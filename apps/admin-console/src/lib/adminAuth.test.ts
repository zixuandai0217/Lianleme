// cover admin login validation and session persistence rules; admin auth helper tests only; verify with npm --workspace apps/admin-console run test -- adminAuth
import { describe, expect, it } from 'vitest'

import {
  buildAdminSession,
  clearAdminSession,
  createMemoryStorage,
  persistAdminSession,
  restoreAdminSession,
  validateAdminLoginDraft,
} from './adminAuth'

describe('validateAdminLoginDraft', () => {
  it('flags empty account and short password', () => {
    expect(
      validateAdminLoginDraft({
        account: '  ',
        password: '1234567',
        rememberDevice: false,
      }),
    ).toEqual({
      account: '请输入管理员账号',
      password: '密码至少需要 8 位字符',
    })
  })
})

describe('buildAdminSession', () => {
  it('creates operator identity from login draft', () => {
    expect(
      buildAdminSession(
        {
          account: 'alex.rivera@lianleme.pro',
          password: 'strong-pass',
          rememberDevice: true,
        },
        '2026-03-21T08:00:00.000Z',
      ),
    ).toMatchObject({
      account: 'alex.rivera@lianleme.pro',
      displayName: 'Alex Rivera',
      roleLabel: '系统管理员',
      avatarLabel: 'AR',
      loginAt: '2026-03-21T08:00:00.000Z',
    })
  })
})

describe('persistAdminSession', () => {
  it('stores remembered sessions in local storage and restores them', () => {
    const storage = createMemoryStorage()
    const session = buildAdminSession(
      {
        account: 'ops@lianleme.pro',
        password: 'strong-pass',
        rememberDevice: true,
      },
      '2026-03-21T08:00:00.000Z',
    )

    persistAdminSession(session, true, storage)

    expect(storage.local.getItem('lianleme.admin.session.local')).toContain('"account":"ops@lianleme.pro"')
    expect(storage.session.getItem('lianleme.admin.session.session')).toBeNull()
    expect(restoreAdminSession(storage)).toMatchObject({
      account: 'ops@lianleme.pro',
      rememberDevice: true,
    })
  })

  it('stores temporary sessions in session storage and restores them', () => {
    const storage = createMemoryStorage()
    const session = buildAdminSession(
      {
        account: 'coach.leo',
        password: 'strong-pass',
        rememberDevice: false,
      },
      '2026-03-21T08:00:00.000Z',
    )

    persistAdminSession(session, false, storage)

    expect(storage.local.getItem('lianleme.admin.session.local')).toBeNull()
    expect(storage.session.getItem('lianleme.admin.session.session')).toContain('"account":"coach.leo"')
    expect(restoreAdminSession(storage)).toMatchObject({
      account: 'coach.leo',
      rememberDevice: false,
    })
  })
})

describe('clearAdminSession', () => {
  it('removes both local and session storage entries', () => {
    const storage = createMemoryStorage()
    const session = buildAdminSession(
      {
        account: 'demo.admin',
        password: 'strong-pass',
        rememberDevice: true,
      },
      '2026-03-21T08:00:00.000Z',
    )

    persistAdminSession(session, true, storage)
    persistAdminSession({ ...session, rememberDevice: false }, false, storage)

    clearAdminSession(storage)

    expect(storage.local.getItem('lianleme.admin.session.local')).toBeNull()
    expect(storage.session.getItem('lianleme.admin.session.session')).toBeNull()
    expect(restoreAdminSession(storage)).toBeNull()
  })
})
