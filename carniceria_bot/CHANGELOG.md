# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-01-23

### Added - Sprint 1 Major Release

#### Security & Authentication
- JWT authentication with role-based access control (RBAC)
- Bcrypt password hashing
- PII encryption at rest using Fernet
- Input sanitization (XSS, SQL injection, path traversal)
- Rate limiting with configurable thresholds
- @require_auth decorator for protected endpoints

#### Performance & Caching
- Redis caching layer with local fallback
- @cached decorator for function result caching
- Cache statistics tracking
- Background task queue with thread pool
- Async operation helpers
- Database optimization with 11 new indices

#### Data Quality
- Enhanced validators (DNI, email, SKU, price, stock)
- Database check constraints (price > 0, stock >= 0)
- Data cleaning automation
- State machine for order lifecycle validation
- Audit logging for state transitions

#### Monitoring & Observability
- Sentry SDK integration with PII filtering
- @track_errors and @track_performance decorators
- Health check endpoints (/health, /health/ready, /health/live)
- Prometheus-compatible metrics endpoint
- Structured logging with JSON support

#### DevOps & Infrastructure
- GitHub Actions CI/CD pipeline
- Multi-version Python testing (3.9, 3.10, 3.11)
- Docker multi-stage builds
- Docker Compose configuration
- Auto-deployment to staging/production
- Environment-specific configurations

#### Testing
- 120+ unit tests across 7 test files
- Integration tests for E2E flows
- Coverage reporting with Codecov
- Pytest fixtures and mocking
- Pre-commit hooks with automated checks

#### User Experience
- Multi-product shopping cart
- Error recovery with clarification questions
- Context management for conversations
- Help command and reset functionality
- Timeout handling with reactivation

#### Analytics
- Conversion funnel tracking
- Customer Lifetime Value (CLV) calculation
- Average Order Value (AOV) metrics
- Cohort analysis
- Real-time metrics dashboard
- Top products reporting

### Changed
- ChatGPT client now includes retry logic (3 attempts, exponential backoff)
- Cost tracking per API request
- 30-second timeout for AI requests
- Mock responses only used as emergency fallback
- Improved error messages throughout

### Fixed
- Database migration handles invalid existing data
- Null byte removal in user inputs
- Email format normalization
- Phone number validation for international formats

### Security
- All PII fields now encrypted at rest
- Secrets moved to environment variables
- No sensitive data in logs
- GDPR-compliant PII filtering in Sentry

## [1.0.0] - 2026-01-20

### Initial Release
- Basic chatbot with OpenAI GPT-4
- Product search and stock management
- Order management (holds, sales)
- WhatsApp integration (Twilio/Meta)
- Email notifications
- MercadoPago payments
- Admin dashboard
- 30+ core features

---

For detailed implementation notes, see `sprint1_final_report.md`
