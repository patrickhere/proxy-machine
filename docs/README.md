# Proxy Machine Documentation

> Complete documentation for The Proxy Machine MTG proxy generation system

---

## Quick Navigation

### 📖 Getting Started
- **[User Guide](guides/GUIDE.md)** - Complete user guide and workflows
- **[Command Reference](guides/REFERENCE.md)** - All available commands and options
- **[Workflow Guide](guides/WORKFLOW.md)** - Engineering conventions and best practices

### 👩‍💻 For Developers
- **[Developer Guide](guides/DEVELOPER_GUIDE.md)** - Setup and contribution guide
- **[Contributing](CONTRIBUTING.md)** - How to contribute to the project
- **[Project Overview](PROJECT_OVERVIEW.md)** - Complete technical documentation (27K words)

### 🚀 Recent Improvements
- **[Quick Start Improvements](improvements/QUICKSTART_IMPROVEMENTS.md)** - 5-minute feature activation
- **[Options A-B-C Complete](improvements/OPTIONS_ABC_COMPLETE.md)** - Infrastructure upgrade summary
- **[Improvements Roadmap](improvements/IMPROVEMENTS_ROADMAP.md)** - Future roadmap (6 months)
- **[Implementation Summary](improvements/IMPLEMENTATION_SUMMARY.md)** - Pragmatic next steps
- **[Reorganization Complete](improvements/REORGANIZATION_COMPLETE.md)** - Project structure cleanup

### 🏗️ Architecture & Planning
- **[Phase 1.5 Summary](planning/PHASE_1.5_SUMMARY.md)** - Phase 1.5 implementation
- **[Phase 2 Summary](planning/PHASE_2_SUMMARY.md)** - Phase 2 implementation
- **[Phase 3 Summary](planning/PHASE_3_SUMMARY.md)** - Phase 3 implementation

### 🌐 Deployment & Sharing
- **[Self-Hosting Guide](deployment/SELF_HOSTING.md)** - Self-host your proxy server
- **[Ubuntu Deployment](deployment/UBUNTU_DEPLOYMENT.md)** - Deploy on Ubuntu Server
- **[Tailscale Deployment](deployment/TAILSCALE_DEPLOYMENT.md)** - Secure deployment with Tailscale
- **[Deployment Quickstart](deployment/DEPLOYMENT_QUICKSTART.md)** - Fast deployment guide

### 👥 Sharing with Friends
- **[Sharing Options](sharing/SHARING_OPTIONS_COMPARISON.md)** - Compare sharing methods
- **[Friend Setup README](sharing/FRIEND_SETUP_README.md)** - Help friends access your server
- **[Network Share Guide](sharing/NETWORK_SHARE_GUIDE.md)** - SMB/NFS network shares
- **[Remote Database Guide](sharing/REMOTE_DATABASE_GUIDE.md)** - Remote database access

### 📚 Archive
- **[AI Recommendations Progress](archive/AI_RECOMMENDATIONS_PROGRESS.md)** - Historical AI recommendations
- **[Roadmap Assessment](archive/ROADMAP_ASSESSMENT.md)** - Original roadmap assessment

---

## Documentation Structure

```
docs/
├── README.md                    # This file
├── CONTRIBUTING.md              # Contribution guidelines
├── PROJECT_OVERVIEW.md          # Complete technical docs
│
├── guides/                      # User & developer guides
│   ├── GUIDE.md                 - User quick-start
│   ├── WORKFLOW.md              - Engineering workflow
│   ├── DEVELOPER_GUIDE.md       - Developer setup
│   └── REFERENCE.md             - Command reference
│
├── improvements/                # Recent upgrades
│   ├── QUICKSTART_IMPROVEMENTS.md
│   ├── OPTIONS_ABC_COMPLETE.md
│   ├── IMPROVEMENTS_ROADMAP.md
│   ├── IMPLEMENTATION_SUMMARY.md
│   ├── REORGANIZATION_PLAN.md
│   └── REORGANIZATION_COMPLETE.md
│
├── planning/                    # Architecture decisions
│   ├── PHASE_1.5_SUMMARY.md
│   ├── PHASE_2_SUMMARY.md
│   └── PHASE_3_SUMMARY.md
│
├── deployment/                  # Server setup guides
│   ├── SELF_HOSTING.md
│   ├── UBUNTU_DEPLOYMENT.md
│   ├── TAILSCALE_DEPLOYMENT.md
│   └── DEPLOYMENT_QUICKSTART.md
│
├── sharing/                     # Friend setup guides
│   ├── SHARING_OPTIONS_COMPARISON.md
│   ├── FRIEND_SETUP_README.md
│   ├── NETWORK_SHARE_GUIDE.md
│   └── REMOTE_DATABASE_GUIDE.md
│
└── archive/                     # Historical docs
    ├── AI_RECOMMENDATIONS_PROGRESS.md
    └── ROADMAP_ASSESSMENT.md
```

---

## Finding What You Need

### I want to...

**...get started using the app**
→ Start with [User Guide](guides/GUIDE.md)

**...contribute code**
→ Check [Developer Guide](guides/DEVELOPER_GUIDE.md) and [Contributing](CONTRIBUTING.md)

**...understand the architecture**
→ Read [Project Overview](PROJECT_OVERVIEW.md)

**...see what's new**
→ Browse [improvements/](improvements/)

**...deploy a server**
→ Follow [deployment/](deployment/) guides

**...share with friends**
→ See [sharing/](sharing/) options

**...understand engineering workflow**
→ Read [Workflow Guide](guides/WORKFLOW.md)

**...look up a command**
→ Check [Command Reference](guides/REFERENCE.md)

---

## Key Features Documented

### Database & Search
- SQLite database with 500K+ cards from Scryfall
- Full-text search (FTS5)
- Type-based land organization (mono, dual, tri, utility)
- Token relationship tracking
- Multi-language support (15+ languages)
- 6-10x faster queries with disk caching

### PDF Generation
- Print-ready layouts (Letter, A4, Tabloid, A3)
- Duplex printing support
- Precise card positioning (2.5" x 3.5")
- Multiple card backs
- Automatic padding for 8-up layouts

### Deck Parsing
- 15+ deck formats supported (Moxfield, Archidekt, MTGA, etc.)
- Token detection and generation
- Deck analysis and reports
- Missing card identification

### Plugin System
- 10+ games supported (MTG, Lorcana, Flesh and Blood, etc.)
- Easy plugin creation

### Infrastructure
- Structured logging with Loguru
- Type-safe configuration with Pydantic
- Disk-based query caching
- Clean, organized project structure

---

## Contributing to Documentation

When adding or updating documentation:

1. **Follow the structure** - Place files in the appropriate directory
2. **Update this index** - Add links to new documents
3. **Use clear headers** - Make docs scannable
4. **Add examples** - Show, don't just tell
5. **Keep it current** - Remove outdated information

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

---

## Support

- **Issues**: Create a GitHub issue
- **Questions**: Check the [User Guide](guides/GUIDE.md) first
- **Discussions**: See the project repository

---

**Happy proxy printing!** 🎴✨
