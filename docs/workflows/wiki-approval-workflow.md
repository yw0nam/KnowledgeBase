# Wiki Approval Workflow

AI 작성 wiki 페이지에 사람 검토 단계를 도입하는 워크플로우.
관련 spec: `docs/superpowers/specs/2026-05-19-wiki-approval-workflow-design.md`.

## Status Model

| Status | 의미 | 다음 상태 |
|---|---|---|
| `not_processed` | AI가 막 작성 — daily-update agent가 아직 안 본 상태 | promote → pending_for_approve, 또는 7d TTL → rejected |
| `pending_for_approve` | 사용자 검토 대기 | approve → approved, reject → rejected (wiki 밖 이동) |
| `approved` | 정식 wiki 콘텐츠 (INDEX.md / subject hub 노출) | 의미 편집 시 not_processed로 self-reset |

## Scope

In-scope page types: `entity`, `concept`, `decision`, `improvement`, `checklist`, `question`.
Out of scope: `summary` (자동 생성), `index`.

## CLI

```
uv run kb-wiki-review list [--status pending_for_approve|not_processed|approved|all] [--counts]
uv run kb-wiki-review promote <stem>                 # daily-update agent용
uv run kb-wiki-review approve <stem> [--feedback "..."]
uv run kb-wiki-review reject  <stem> [--feedback "..."]
uv run kb-wiki-review ttl-sweep [--days 7]           # cron only
```

Empty `--feedback` (또는 interactive prompt에서 enter만) → User Feedback 라인 미추가.

## Daily-update agent contract

`scripts/cron/kb-wiki-promote.sh` 가 매일 04:00 KST 실행 (`kb-memory-daily` 30분 후).
수동으로 invoke할 수도 있음.

1. Input — uncommitted 변경분 우선 확인:
   ```bash
   git -C data status --short          # 오늘 daily build가 만든 신규 파일 파악
   uv run kb-wiki-review list --status not_processed
   ```
2. 각 페이지에 대해 LLM 판단 (신규 uncommitted 페이지 우선):
   - 소스가 명확하고 검증 가능한가?
   - 다른 wiki/handoff에서 참조될 가능성이 있는가?
   - 이벤트 dump가 아닌 *지식*인가 (시간이 지나도 가치 유지)?
3. Promote:
   ```bash
   uv run kb-wiki-review promote <stem>
   ```
4. Leave: 아무것도 안 함. 다음 날 재고려. 7일째 자동 TTL.
5. Handoff + log: `data/handoffs/YYYY/MM/wiki-promote/` 에 결과 기록.
6. Promoted 페이지가 있으면 nested `data/` repo commit:
   ```
   promote: YYYY-MM-DD wiki promotion
   ```
   Push는 하지 않음.

**금지**: agent는 직접 reject 안 함. 사람만 reject. TTL이 deterministic 안전망.

## TTL cron

`scripts/cron/kb-wiki-ttl-sweep.sh` 가 매일 00:30 KST 실행 권장:

```cron
30 0 * * * /home/spow12/codes/KnowledgeBase/scripts/cron/kb-wiki-ttl-sweep.sh
```

`created` 가 7일 이전인 `not_processed` 페이지를 자동 reject (rejected_by=auto_ttl).

## Approved 페이지 수정 정책

- Semantic 변화 (사실 변경, 새 정보 추가, 결론 수정): `review_status: not_processed` 로 self-reset. 다음 daily-update에서 재promote 후보.
- Typo / 포매팅: status 유지.

Deterministic 감지 없음. CLAUDE.md 가이드라인 + agent 판단에 의존.

## Subject `_index.md` hub

Approve 후 사용자(또는 agent)가 subject hub에 `- [[<stem>]]` 라인 수동 추가. Lint가 missing entry를 warning으로 알려줌. 자동 동기화는 별도 작업.

## Rejected 파일 보존

거절된 페이지는 `data/rejected/<원래 wiki path>` 로 git mv. Wiki 트리 깨끗, audit 데이터는 패턴 분석용으로 보존. `data/rejected/` 는 lint scope 밖.

## Walkthrough

자세한 happy/reject/TTL/edit 시나리오는 spec §10 참고.
