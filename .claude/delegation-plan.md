## Delegation Plan

### Overview
Fix preview page table display issues and add policy merge analysis functionality to show merge statistics before push.

### Parallel Group 1: Investigation and API Enhancement
Dependencies: none

| Task | Agent | Description | Files |
|------|-------|-------------|-------|
| 1.1 | researcher | Research the root cause of table display issue - investigate how formattedData is populated from backend API, check if column names match between frontend and backend, and verify data structure consistency | frontend/src/views/workflow/PreviewStep.vue, frontend/src/views/PreviewPage.vue, frontend/src/store/order.ts, backend/app/api/orders.py |
| 1.2 | software-engineer | Add merge analysis API endpoint to frontend API client - create getMergeAnalysis function that calls POST /api/push/orders/{orderId}/merge | frontend/src/api/firewall.ts |

### Parallel Group 2: Fix Table Display and Add Merge UI
Dependencies: Group 1

| Task | Agent | Description | Files |
|------|-------|-------------|-------|
| 2.1 | software-engineer | Fix table display in PreviewStep.vue based on research findings - ensure columns are correctly extracted from data, handle missing/undefined fields, add proper null checks, and verify firewall grouping logic works correctly | frontend/src/views/workflow/PreviewStep.vue |
| 2.2 | software-engineer | Add merge analysis section to PreviewStep.vue - add "策略合并分析" card above statistics showing original count vs merged count, redundant policy count, merge button to trigger analysis, and display merge results in expandable section | frontend/src/views/workflow/PreviewStep.vue |

### Parallel Group 3: Sync PreviewPage and Add Tests
Dependencies: Group 2

| Task | Agent | Description | Files |
|------|-------|-------------|-------|
| 3.1 | software-engineer | Apply same table display fixes to PreviewPage.vue to maintain consistency with PreviewStep.vue | frontend/src/views/PreviewPage.vue |
| 3.2 | qa | Write unit tests for preview components - test data loading, column extraction, firewall grouping, merge analysis display, and error handling | frontend/tests/PreviewStep.spec.ts (new), frontend/tests/PreviewPage.spec.ts (new) |

### Parallel Group 4: Review and Validation
Dependencies: Group 3

| Task | Agent | Description | Files |
|------|-------|-------------|-------|
| 4.1 | code-reviewer | Review all preview page changes for code quality, TypeScript usage, Element Plus best practices, error handling, and UI/UX consistency | frontend/src/views/workflow/PreviewStep.vue, frontend/src/views/PreviewPage.vue, frontend/src/api/firewall.ts |

### Quality Gates
- [ ] Table columns display correctly with proper data binding
- [ ] Firewall grouping works and shows correct policy counts
- [ ] Merge analysis API integration works and displays results
- [ ] Both PreviewStep.vue and PreviewPage.vue have consistent behavior
- [ ] No console errors or warnings
- [ ] TypeScript types are properly defined
- [ ] Unit tests pass with good coverage
- [ ] Code review approved
