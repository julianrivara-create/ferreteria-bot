# Quick Start Guide - Bot Sales

## 🚀 Deployment en 5 Minutos

### Option A: Docker Compose (Recomendado)

```bash
# 1. Clone y configurar
git clone <repo>
cd iphone-bot-demo
cp .env.development .env

# 2. Editar .env con tus credenciales
nano .env

# 3. Build y start
docker-compose up --build

# 4. Ver logs
docker-compose logs -f bot

# 5. Acceder
# Bot: http://localhost:5000
# Dashboard: http://localhost:5001
```

### Option B: Local Development

```bash
# 1. Setup Python
python3 -m venv .venv
source .venv/bin/activate  # o .venv\Scripts\activate en Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.development .env
nano .env

# 4. Run migrations
python3 migrations/001_add_indices_and_constraints.py

# 5. Start Redis (opcional pero recomendado)
redis-server

# 6. Run bot
python whatsapp_server.py

# 7. Run dashboard (otra terminal)
cd dashboard && python app.py
```

## ⚙️ Configuración Mínima Requerida

```bash
# .env
OPENAI_API_KEY=sk-...  # REQUERIDO
DATABASE_PATH=data/ferreteria.db
LOG_FILE=data/sales_bot.log

# Opcionales pero recomendados
REDIS_URL=redis://localhost:6379/0
SENTRY_DSN=https://...@sentry.io/...
JWT_SECRET=your-secret-key-here
ENCRYPTION_PASSWORD=your-encryption-password
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=bot_sales --cov-report=html

# Specific test file
pytest tests/test_validators.py -v

# Integration tests only
pytest tests/test_integration.py -v
```

## 📊 Health Checks

```bash
# Basic health
curl http://localhost:5000/health

# Readiness (checks dependencies)
curl http://localhost:5000/health/ready

# Metrics (Prometheus format)
curl http://localhost:5000/metrics
```

## 🔑 Características Principales

### Security ✅
- JWT authentication con RBAC
- PII encryption at rest
- Input sanitization (XSS, SQL, path traversal)
- Rate limiting
- Bcrypt password hashing

### Performance ✅
- Redis caching (60%+ cost savings)
- Background tasks
- Database indices (11)
- Async operations

### Monitoring ✅
- Sentry error tracking
- Performance metrics
- Structured logging
- Health checks

### Testing ✅
- 120+ unit tests
- Integration tests
- CI/CD pipeline
- Coverage > 70%

## 🐛 Troubleshooting

### "Redis connection failed"
→ Opcional. Bot funciona con local cache. Para usar Redis:
```bash
redis-server
```

### "OpenAI API error"
→ Verificar API key en `.env`:
```bash
echo $OPENAI_API_KEY
```

### "Database locked"
→ Cerrar otras conexiones:
```bash
lsof data/ferreteria.db
kill <PID>
```

### Tests failing
→ Install test dependencies:
```bash
pip install pytest pytest-cov pytest-mock
```

## 📚 Documentación

- `/docs/security_performance_integration.md` - Integration examples
- `/sprint1_final_report.md` - Implementation details
- `/PRODUCTION_GUIDE.md` - Production deployment
- `/PROJECT_COMPLETE.md` - Feature list

## 🆘 Support

1. Check logs: `tail -f data/sales_bot.log`
2. Health check: `curl http://localhost:5000/health/ready`
3. Sentry dashboard (si configurado)
4. GitHub Issues

## 🎯 Next Steps

1. ✅ Configurar todas las API keys reales
2. ✅ Run migrations
3. ✅ Run tests
4. ✅ Start services
5. ⏸️ Deploy to staging (Railway/Heroku)
6. ⏸️ Run smoke tests
7. ⏸️ Deploy to production

---

**Listo en 5 minutos!** 🚀
