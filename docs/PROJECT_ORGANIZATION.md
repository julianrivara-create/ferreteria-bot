# Project Organization - Updated Structure

## 📁 Clean Directory Structure

```
iphone-bot-demo/
├── bot_sales/           # ✅ Application code (organized)
├── tests/               # ✅ All tests (130+)
├── dashboard/           # ✅ Admin interface
├── migrations/          # ✅ Database migrations
├── data/                # ✅ SQLite DB, CSVs, logs
├── docs/                # ✅ All documentation
│   ├── project/         # Production & project docs
│   └── *.md             # Feature-specific guides
├── config/              # ✅ Configuration files
├── examples/            # ✅ Usage examples
├── .github/workflows/   # ✅ CI/CD
├── .git-hooks/          # ✅ Pre-commit hooks
├── scripts/             # ✅ Deployment scripts
│   └── deployment/      # Procfile, runtime.txt
├── static/              # ✅ Static assets
├── archive/             # 📦 Archived/old files
│   └── powershell/      # PowerShell scripts (different project)
│
└── Root Files (Clean!)  # ✅ Only essential files
    ├── README.md
    ├── QUICKSTART.md
    ├── CHANGELOG.md
    ├── CONTRIBUTING.md
    ├── SECURITY_AUDIT.md
    ├── requirements.txt
    ├── Dockerfile
    ├── docker-compose.yml
    ├── .gitignore
    ├── .env.development
    ├── .env.production
    ├── .env.example
    ├── whatsapp_server.py
    └── bot_cli.py
```

## 🗂️ What Was Organized

### Moved to `/docs/project/`
- ✅ `PROJECT_COMPLETE.md` → More details in project docs
- ✅ `PRODUCTION_GUIDE.md` → Production deployment guide

### Moved to `/scripts/deployment/`
- ✅ `Procfile` → Railway/Heroku deployment
- ✅ `runtime.txt` → Python version spec

### Moved to `/archive/powershell/`
- ✅ `DailyReport_v5.2.ps1` → PowerShell project (different project)

### Kept in Root (Essential Only)
- ✅ `README.md` - Main documentation
- ✅ `QUICKSTART.md` - Quick setup guide
- ✅ `CHANGELOG.md` - Version history
- ✅ `CONTRIBUTING.md` - Dev guidelines
- ✅ `SECURITY_AUDIT.md` - Security checklist
- ✅ `requirements.txt` - Dependencies
- ✅ `Dockerfile` - Container build
- ✅ `docker-compose.yml` - Stack definition
- ✅ Environment files (.env.*)
- ✅ Entry points (whatsapp_server.py, bot_cli.py)

## 📌 Navigation Guide

| Need... | Go to... |
|---------|----------|
| **Quick setup** | [QUICKSTART.md](../QUICKSTART.md) |
| **All features** | [docs/project/PROJECT_COMPLETE.md](project/PROJECT_COMPLETE.md) |
| **Production deploy** | [docs/project/PRODUCTION_GUIDE.md](project/PRODUCTION_GUIDE.md) |
| **Security** | [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) |
| **Contributing** | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| **API integration** | [security_performance_integration.md](security_performance_integration.md) |
| **Analytics** | [ANALYTICS_GUIDE.md](ANALYTICS_GUIDE.md) |
| **Email setup** | [email_plan.md](email_plan.md) |
| **MercadoPago** | [mp_integration_plan.md](mp_integration_plan.md) |

## 🎯 Benefits of New Structure

1. **Cleaner Root** - Only 15 files vs 30+ before
2. **Logical Grouping** - Related files together
3. **Easy Navigation** - Clear hierarchy
4. **Scalable** - Ready for growth
5. **Professional** - Standard project layout

## 🔄 Migration Notes

- All import paths unchanged (no code changes needed)
- Documentation links updated in README
- Archive folder for old/unrelated files
- No functionality broken

---

Last Updated: 2026-01-23
