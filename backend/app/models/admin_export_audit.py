"""管理后台导出审计：每一次导出尝试一条记录（工单 38）。

审计是「数据流出可追溯」的唯一凭据，因此被拒绝的那次导出同样落库：``outcome``
取 ``success`` / ``rejected``，成功时 ``rejection_reason`` 为空，被拒时写入可读原因。
记录只追加、不更新：管理端只提供只读查询接口。
"""
import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

OUTCOME_SUCCESS = "success"
OUTCOME_REJECTED = "rejected"


class AdminExportAudit(Base):
    """一次导出尝试（成功或被拒）的审计记录。

    ``filter_summary`` 是规范化后的筛选条件摘要（只含显式传入的条件 + 排序），
    ``filter_hash`` 是同一摘要的短哈希，与下载文件名中的哈希一致，用于把
    「某个文件」对回「哪次导出」。``operator_id`` 即发起导出的管理员。
    """

    __tablename__ = "admin_export_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filter_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    filter_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    # 成功时是实际导出行数；被拒时是「若导出会有多少行」，便于运营判断该收窄到什么程度。
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    operator = relationship("User")
