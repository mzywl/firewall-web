## Task Plan

### Overview
Complete the remaining features for the firewall policy automation system. The system already has Excel upload/parsing, IP formatting, table editing, version tracking, and basic push infrastructure (WebSocket, Celery, policy merger). The remaining work includes: enhancing the preview page with merge analysis, implementing SSH-based firewall push logic for 4 firewall types, building the history page with filtering/search, and creating the firewall configuration management interface.

### Tasks

1. **Enhance Preview Page with Merge Analysis**
   - Description: Add policy merge preview functionality to PreviewStep.vue, showing original vs merged policy counts, redundant policy detection, and merge details before push
   - Package/files: frontend/src/views/workflow/PreviewStep.vue, frontend/src/views/PreviewPage.vue
   - Dependencies: none
   - Complexity: Low
   - Agent: software-engineer

2. **Implement SSH Connection Manager**
   - Description: Create SSH connection management service using Paramiko with connection pooling, timeout control, password/key authentication, and connection testing
   - Package/files: backend/app/services/ssh_manager.py (new)
   - Dependencies: none
   - Complexity: Medium
   - Agent: software-engineer

3. **Implement Firewall Command Generators**
   - Description: Create command generator classes for 4 firewall types (Fortigate, Hillstone, Leadsec, H3C) that convert policy objects into vendor-specific CLI commands
   - Package/files: backend/app/services/firewall_commands.py (new)
   - Dependencies: none
   - Complexity: High
   - Agent: software-engineer

4. **Implement Real Firewall Push Service**
   - Description: Replace mock push logic in push_tasks.py with real SSH-based push using ssh_manager and firewall_commands, including error handling, retry logic, and detailed logging
   - Package/files: backend/app/tasks/push_tasks.py, backend/app/services/firewall_push.py (new)
   - Dependencies: 2, 3
   - Complexity: High
   - Agent: software-engineer

5. **Build History Page Frontend**
   - Description: Implement HistoryPage.vue with order list table (pagination, sorting), filters (status, date range, creator), order detail view, and actions (re-push, export, delete)
   - Package/files: frontend/src/views/HistoryPage.vue
   - Dependencies: none
   - Complexity: Medium
   - Agent: software-engineer

6. **Build History API Endpoints**
   - Description: Add API endpoints to orders.py for listing orders with filters/pagination, getting order details with policies and logs, re-push functionality, and export to Excel
   - Package/files: backend/app/api/orders.py
   - Dependencies: none
   - Complexity: Low
   - Agent: software-engineer

7. **Build Firewall Config Management Frontend**
   - Description: Implement ConfigPage.vue with firewall list table, add/edit firewall dialog, connection test button, firewall grouping, and status indicators
   - Package/files: frontend/src/views/ConfigPage.vue
   - Dependencies: none
   - Complexity: Medium
   - Agent: software-engineer

8. **Build Firewall Config API**
   - Description: Create firewalls.py API with CRUD endpoints for firewall management, connection test endpoint using SSH manager, and firewall grouping logic
   - Package/files: backend/app/api/firewalls.py (new)
   - Dependencies: 2
   - Complexity: Medium
   - Agent: software-engineer

9. **Add Firewall IP Range Management**
   - Description: Extend Firewall model and API to support IP range configuration for automatic firewall matching, update firewall_matcher.py to use database ranges
   - Package/files: backend/app/models/__init__.py, backend/app/core/firewall_matcher.py, backend/alembic/versions/005_add_firewall_ranges.py (new)
   - Dependencies: none
   - Complexity: Medium
   - Agent: software-engineer

10. **Enhance Policy Merge Algorithm**
    - Description: Improve policy_merger.py to handle IP range merging (10.1.1.1, 10.1.1.2, 10.1.1.3 → 10.1.1.1-10.1.1.3), preserve CIDR notation, and implement smarter redundancy detection
    - Package/files: backend/app/core/policy_merger.py
    - Dependencies: none
    - Complexity: Medium
    - Agent: software-engineer

11. **Write Unit Tests for SSH and Push Services**
    - Description: Create unit tests for ssh_manager, firewall_commands, and firewall_push services with mocked SSH connections and firewall responses
    - Package/files: backend/tests/test_ssh_manager.py (new), backend/tests/test_firewall_commands.py (new), backend/tests/test_firewall_push.py (new)
    - Dependencies: 2, 3, 4
    - Complexity: Medium
    - Agent: qa

12. **Write Integration Tests for Push Flow**
    - Description: Create end-to-end tests for the complete push workflow from order creation to policy push completion, using test database and mocked SSH
    - Package/files: backend/tests/test_push_integration.py (new)
    - Dependencies: 4, 11
    - Complexity: Medium
    - Agent: qa

13. **Write Frontend Component Tests**
    - Description: Create unit tests for PreviewPage, HistoryPage, and ConfigPage components using Vue Test Utils
    - Package/files: frontend/tests/PreviewPage.spec.ts (new), frontend/tests/HistoryPage.spec.ts (new), frontend/tests/ConfigPage.spec.ts (new)
    - Dependencies: 1, 5, 7
    - Complexity: Low
    - Agent: qa

14. **Code Review - Backend Services**
    - Description: Review SSH manager, firewall commands, and push service implementations for security, error handling, code quality, and best practices
    - Package/files: backend/app/services/*, backend/app/tasks/push_tasks.py
    - Dependencies: 2, 3, 4
    - Complexity: Low
    - Agent: code-reviewer

15. **Code Review - Frontend Pages**
    - Description: Review PreviewPage, HistoryPage, and ConfigPage implementations for UI/UX consistency, TypeScript usage, and Element Plus best practices
    - Package/files: frontend/src/views/PreviewPage.vue, frontend/src/views/HistoryPage.vue, frontend/src/views/ConfigPage.vue
    - Dependencies: 1, 5, 7
    - Complexity: Low
    - Agent: code-reviewer

16. **Security Audit - SSH and Credentials**
    - Description: Audit SSH connection handling, credential storage (ensure encryption), paramiko usage for command injection vulnerabilities, and firewall command generation for injection risks
    - Package/files: backend/app/services/ssh_manager.py, backend/app/services/firewall_commands.py, backend/app/models/__init__.py
    - Dependencies: 2, 3, 8
    - Complexity: Medium
    - Agent: security

17. **Security Audit - API Endpoints**
    - Description: Review all API endpoints for authentication/authorization, input validation, SQL injection risks, and sensitive data exposure
    - Package/files: backend/app/api/*.py
    - Dependencies: 6, 8
    - Complexity: Low
    - Agent: security

### Risks & Considerations

- **SSH Connection Stability**: Network issues, firewall timeouts, and authentication failures need robust error handling and retry mechanisms
- **Firewall Command Compatibility**: Each firewall vendor has different CLI syntax; commands must be thoroughly tested with real devices or accurate simulators
- **Credential Security**: Firewall passwords must be encrypted at rest; consider using environment variables or secret management systems
- **Concurrent Push Operations**: Multiple simultaneous pushes to the same firewall could cause conflicts; implement locking or queuing
- **WebSocket Connection Management**: Ensure WebSocket connections are properly cleaned up when push operations complete or fail
- **Database Migration**: Adding IP range fields to Firewall model requires careful migration to avoid breaking existing data
- **Performance**: Policy merge algorithm may be slow with large datasets (1000+ policies); consider optimization or background processing
- **Testing Limitations**: Real firewall testing requires access to physical/virtual devices; mock testing may miss edge cases

### Architecture Decisions

- **SSH Connection Pooling**: Use a connection pool pattern to reuse SSH connections for multiple policy pushes to the same firewall, reducing overhead
- **Command Generation Strategy**: Use factory pattern for firewall command generators to easily add new firewall types in the future
- **Credential Encryption**: Use Fernet (symmetric encryption) from cryptography library to encrypt firewall passwords before storing in database
- **Push Task Isolation**: Each firewall push should be an independent Celery task to enable parallel execution and individual retry logic
- **IP Range Storage**: Store IP ranges as JSON array in Firewall model for flexibility, with indexed queries for matching performance
- **Merge Algorithm Approach**: Implement merge as a separate analysis step (not automatic) so users can review before applying
- **Error Recovery**: Implement transaction rollback for failed pushes and maintain detailed operation logs for debugging
- **API Pagination**: Use cursor-based pagination for history page to handle large datasets efficiently
