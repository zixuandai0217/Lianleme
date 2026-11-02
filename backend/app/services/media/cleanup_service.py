"""媒体资产清理服务：记录删除、用户级清空、孤儿巡检与反向降级。

清理是维护路径，不是请求链路：单批数量受配置约束、按批提交，任何一次调用都不会
持有一个覆盖全部数据的长事务。每个路径都可重入——重复执行只会得到更少的待清理项，
第二次调用通常返回全零。对象是否「孤儿」只由资产表（任意状态）是否引用决定，
是否「够老」由存储层给出的对象年龄决定。
"""
import datetime
import logging
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import (
    EVENT_MEDIA_ASSET_DEGRADED,
    EVENT_MEDIA_CLEANUP_COMPLETED,
    FIELD_ASSET_ID,
    FIELD_BATCHES,
    FIELD_DEGRADED_ASSETS,
    FIELD_DELETED_ASSETS,
    FIELD_DELETED_OBJECTS,
    FIELD_KIND,
    FIELD_SCANNED,
    FIELD_SCOPE,
    FIELD_SKIPPED_YOUNG,
    FIELD_USER_ID,
    log_event,
)
from app.core.storage import Storage, StorageError
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
from app.models.media_asset import (
    ASSET_STATUS_AVAILABLE,
    ASSET_STATUS_DEGRADED,
    ASSET_STATUS_DELETED,
    ASSET_STATUS_PENDING_DELETE,
    MediaAsset,
)

logger = logging.getLogger(__name__)

# 清理事件里的 scope 取值：同一事件名承载三条清理路径，靠 scope 区分。
SCOPE_RECORD = "record"
SCOPE_USER = "user"
SCOPE_ORPHAN = "orphan"

_T = TypeVar("_T")


def cleanup_batch_size() -> int:
    """单批处理数量上限；配置为 0 或负数时回落到 1，避免死循环。"""
    return max(1, int(settings.MEDIA_CLEANUP_BATCH_SIZE))


def orphan_grace_seconds() -> float:
    """孤儿宽限期（秒）；负数按 0 处理，即所有孤儿都算够老。"""
    return float(max(0, int(settings.MEDIA_ORPHAN_GRACE_SECONDS)))


def environment_prefix() -> str:
    """当前环境的对象前缀：``{APP_ENV}/``。"""
    return f"{settings.APP_ENV.strip('/')}/"


def user_prefix(user_id: int) -> str:
    """单个用户的对象前缀：``{APP_ENV}/{user_id}/``。

    结尾的斜杠保证用户 1 的前缀不会匹配到用户 12 的对象。
    """
    return f"{environment_prefix()}{user_id}/"


def _chunks(items: Sequence[_T], size: int) -> Iterator[Sequence[_T]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@dataclass
class CleanupResult:
    """一次清理调用的计数（接口响应与结构化日志共用同一份事实）。"""

    scanned: int = 0
    deleted_objects: int = 0
    deleted_assets: int = 0
    degraded_assets: int = 0
    skipped_young: int = 0
    batches: int = 0


class CleanupService:
    """资产清理入口；业务代码只依赖本服务与存储端口。"""

    def __init__(self, db: AsyncSession, storage: Storage) -> None:
        self._db = db
        self._storage = storage

    # ── 删除一条分析记录引用的资产 ──

    async def delete_record_assets(self, asset_ids: Collection[str]) -> CleanupResult:
        """删除记录引用的原图与缩略图资产。

        调用方必须**先删除记录并提交**，这样「是否仍被其他记录/任务引用」的检查
        不会再看到自己。仍被引用的资产保持原状（不删对象、不改状态）。
        """
        unique_ids = {asset_id for asset_id in asset_ids if asset_id}
        if not unique_ids:
            return CleanupResult()

        assets = await self._load_assets(unique_ids)
        if not assets:
            return CleanupResult()
        referenced = await self._referenced_asset_ids(unique_ids)
        removable = [asset for asset in assets if asset.asset_id not in referenced]

        result = CleanupResult()
        now = _utc_now()
        for batch in _chunks(removable, cleanup_batch_size()):
            for asset in batch:
                asset.status = ASSET_STATUS_PENDING_DELETE
            await self._db.commit()

            for asset in batch:
                try:
                    await self._storage.delete(asset.object_key)
                except StorageError:
                    # 对象删不掉时保留 pending_delete：下一次清理还能看到它，
                    # 也绝不把它错标成已删除（旧签名链接必须真的失效）。
                    logger.warning(
                        "媒体资产对象删除失败，保留待清理状态",
                        extra={FIELD_ASSET_ID: asset.asset_id},
                    )
                    continue
                asset.status = ASSET_STATUS_DELETED
                asset.deleted_at = now
                result.deleted_objects += 1
                result.deleted_assets += 1
            await self._db.commit()
            result.batches += 1

        _log_cleanup(SCOPE_RECORD, result)
        return result

    # ── 按用户前缀清空 ──

    async def purge_user_assets(self, user_id: int) -> CleanupResult:
        """按 ``{env}/{user_id}/`` 前缀删除该用户的全部对象，并标记资产行已删除。

        对象与资产行都按批处理、按批提交；重复执行不会报错，第二次返回全零。
        只触碰该用户自己的前缀：其他用户的对象既不会被列举也不会被删除。
        """
        objects = await self._storage.list_objects(user_prefix(user_id))
        assets = await self._load_user_assets(user_id)

        result = CleanupResult()
        now = _utc_now()
        expected_keys = {obj.key for obj in objects}

        # 先删对象（按批提交），再标记资产行（按批提交）：只有对象确实不存在时
        # 才把资产标成已删除，删除失败的行留在待清理队列里等下一次重试。
        deleted_keys: set[str] = set()
        object_batch_count = 0
        for batch in _chunks(objects, cleanup_batch_size()):
            for obj in batch:
                try:
                    await self._storage.delete(obj.key)
                except StorageError:
                    logger.warning("用户级清理未能删除对象，留待清理队列重试")
                    continue
                deleted_keys.add(obj.key)
                result.deleted_objects += 1
            await self._db.commit()
            object_batch_count += 1

        asset_batch_count = 0
        for batch in _chunks(assets, cleanup_batch_size()):
            for asset in batch:
                if asset.object_key in deleted_keys or asset.object_key not in expected_keys:
                    asset.status = ASSET_STATUS_DELETED
                    asset.deleted_at = now
                    result.deleted_assets += 1
                else:
                    asset.status = ASSET_STATUS_PENDING_DELETE
            await self._db.commit()
            asset_batch_count += 1

        # 批次数按两个阶段中较大者计：对象与资产一一对应时不会翻倍。
        result.batches = max(object_batch_count, asset_batch_count)

        _log_cleanup(SCOPE_USER, result, user_id=user_id)
        return result

    # ── 孤儿巡检（正向 + 反向） ──

    async def retry_pending_delete_assets(self) -> CleanupResult:
        """重试「待清理」队列：删除对象、标记资产已删除（分批、可重入）。

        这是删除失败后的唯一恢复路径：``pending_delete`` 行属于清理队列而不是
        「仍被引用」，因此巡检不会再把它们当挡箭牌，也不会永远留在存储里。
        """
        result = CleanupResult()
        assets = await self._load_assets_by_status(ASSET_STATUS_PENDING_DELETE)
        now = _utc_now()
        for batch in _chunks(assets, cleanup_batch_size()):
            for asset in batch:
                try:
                    await self._storage.delete(asset.object_key)
                except StorageError:
                    logger.warning(
                        "待清理资产的对象仍未删掉，保留状态等待下次重试",
                        extra={FIELD_ASSET_ID: asset.asset_id},
                    )
                    continue
                asset.status = ASSET_STATUS_DELETED
                asset.deleted_at = now
                result.deleted_objects += 1
                result.deleted_assets += 1
            await self._db.commit()
            result.batches += 1
        return result

    async def sweep_orphans(self) -> CleanupResult:
        """跑一批孤儿巡检：删旧孤儿、降级「记录在但对象丢」的资产。

        正向：列出 ``{APP_ENV}/`` 下的对象，与资产表（任意状态）比对；未被引用且
        超过宽限期的对象删除，未超过宽限期的保持不动。为避免后段对象永远轮不到，
        每次只取「最老的未被引用对象」中的一批：够老的就删掉，不够老的下次仍是
        候选，等它变老后再删。

        反向：对象清单里找不到的可用资产置为 ``degraded`` 并逐条记事件；这条路径
        不需要逐个 ``exists`` 探测，直接用清单集合做差集，一次调用覆盖全部可用资产。
        """
        # 先把上一轮删除失败的「待清理」队列再试一遍；它属于清理队列而不是孤儿。
        result = await self.retry_pending_delete_assets()
        prefix = environment_prefix()
        objects = await self._storage.list_objects(prefix)
        existing_keys = {obj.key for obj in objects}
        referenced_keys = await self._referenced_keys(prefix)

        grace = orphan_grace_seconds()
        candidates = sorted(
            (obj for obj in objects if obj.key not in referenced_keys),
            key=lambda obj: (-obj.age_seconds, obj.key),
        )
        page = candidates[:cleanup_batch_size()]
        result.scanned = len(page)
        for obj in page:
            if obj.age_seconds < grace:
                result.skipped_young += 1
                continue
            try:
                await self._storage.delete(obj.key)
            except StorageError:
                logger.warning("孤儿对象删除失败，留待下次巡检")
                continue
            result.deleted_objects += 1
        if page:
            await self._db.commit()
            result.batches += 1

        degraded = await self._degrade_missing_assets(prefix, existing_keys)
        result.degraded_assets = len(degraded)
        if degraded:
            await self._db.commit()
            result.batches += 1

        _log_cleanup(SCOPE_ORPHAN, result)
        return result

    async def _degrade_missing_assets(
        self, prefix: str, existing_keys: set[str]
    ) -> list[MediaAsset]:
        """把「可用但对象不在清单里」的资产标记降级，逐条记降级事件。

        一次最多处理一批；已降级的行不再是候选，所以后续巡检会继续往后覆盖。
        """
        result = await self._db.execute(
            select(MediaAsset)
            .where(
                MediaAsset.status == ASSET_STATUS_AVAILABLE,
                MediaAsset.object_key.startswith(prefix),
            )
            .order_by(MediaAsset.created_at, MediaAsset.asset_id)
        )
        missing = [
            asset
            for asset in result.scalars().all()
            if asset.object_key not in existing_keys
        ][:cleanup_batch_size()]

        for asset in missing:
            asset.status = ASSET_STATUS_DEGRADED
            # 只带标识与分类字段：不含对象 key、不含 URL、不含图片内容。
            log_event(
                logger,
                EVENT_MEDIA_ASSET_DEGRADED,
                message="资产对象缺失，已标记降级",
                level=logging.WARNING,
                **{
                    FIELD_ASSET_ID: asset.asset_id,
                    FIELD_KIND: asset.kind,
                    FIELD_USER_ID: asset.user_id,
                },
            )
        return missing

    # ── 查询辅助 ──

    async def _load_assets(self, asset_ids: Collection[str]) -> list[MediaAsset]:
        result = await self._db.execute(
            select(MediaAsset).where(
                MediaAsset.asset_id.in_(list(asset_ids)),
                MediaAsset.status != ASSET_STATUS_DELETED,
            )
        )
        return list(result.scalars().all())

    async def _load_assets_by_status(self, status: str) -> list[MediaAsset]:
        result = await self._db.execute(
            select(MediaAsset)
            .where(MediaAsset.status == status)
            .order_by(MediaAsset.created_at, MediaAsset.asset_id)
        )
        return list(result.scalars().all())

    async def _load_user_assets(self, user_id: int) -> list[MediaAsset]:
        result = await self._db.execute(
            select(MediaAsset)
            .where(
                MediaAsset.user_id == user_id,
                MediaAsset.status != ASSET_STATUS_DELETED,
            )
            .order_by(MediaAsset.created_at, MediaAsset.asset_id)
        )
        return list(result.scalars().all())

    async def _referenced_asset_ids(self, asset_ids: Collection[str]) -> set[str]:
        """仍被其他记录或任务引用的资产标识（这些资产不能删）。"""
        targets = sorted(asset_ids)
        referenced: set[str] = set()

        records = await self._db.execute(
            select(BodyAnalysisRecord).where(
                or_(
                    BodyAnalysisRecord.image_asset_id.in_(targets),
                    BodyAnalysisRecord.thumbnail_asset_id.in_(targets),
                )
            )
        )
        for record in records.scalars().all():
            for asset_id in (record.image_asset_id, record.thumbnail_asset_id):
                if asset_id in targets:
                    referenced.add(asset_id)

        # 只有进行中的任务需要保住输入资产；已完成任务只是执行记录，
        # 用户删除分析记录后照片必须真正消失（否则 AC1 的「删除是真的删除」不成立）。
        tasks = await self._db.execute(
            select(AnalysisTask).where(
                AnalysisTask.status.in_(("pending", "processing")),
                or_(
                    AnalysisTask.image_asset_id.in_(targets),
                    AnalysisTask.thumbnail_asset_id.in_(targets),
                ),
            )
        )
        for task in tasks.scalars().all():
            for asset_id in (task.image_asset_id, task.thumbnail_asset_id):
                if asset_id in targets:
                    referenced.add(asset_id)
        return referenced

    async def _referenced_keys(self, prefix: str) -> set[str]:
        """仍应保留对象 key 的资产行：可用与已降级。

        ``pending_delete`` / ``deleted`` 行属于「队列里等待消失」的资产，不能再用
        它们给对象做挡箭牌，否则一次删除失败会让对象永久留在存储里。
        """
        result = await self._db.execute(
            select(MediaAsset.object_key).where(
                MediaAsset.object_key.startswith(prefix),
                MediaAsset.status.in_((ASSET_STATUS_AVAILABLE, ASSET_STATUS_DEGRADED)),
            )
        )
        return set(result.scalars().all())


def _log_cleanup(scope: str, result: CleanupResult, *, user_id: int | None = None) -> None:
    """一次清理调用只记一条计数事件；没有实际批次时不打扰日志。"""
    if result.batches == 0:
        return
    fields: dict[str, object] = {
        FIELD_SCOPE: scope,
        FIELD_BATCHES: result.batches,
        FIELD_SCANNED: result.scanned,
        FIELD_DELETED_OBJECTS: result.deleted_objects,
        FIELD_DELETED_ASSETS: result.deleted_assets,
        FIELD_DEGRADED_ASSETS: result.degraded_assets,
        FIELD_SKIPPED_YOUNG: result.skipped_young,
    }
    if user_id is not None:
        fields[FIELD_USER_ID] = user_id
    log_event(
        logger,
        EVENT_MEDIA_CLEANUP_COMPLETED,
        message="媒体资产清理完成",
        **fields,
    )
