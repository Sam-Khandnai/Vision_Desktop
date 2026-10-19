# Vision · ویژن

**فارسی** · [English](#english)

دستیار هوش مصنوعی دسکتاپ — کاملاً محلی. مدل‌های سازگار با OpenAI + ابزارهای MCP، با رابط تیره و فیروزه‌ای، فارسی و انگلیسی.
فقط برای صحبت با API مدل و سرورهای MCP به اینترنت وصل می‌شود؛ گفتگوها، حافظه و تنظیمات روی همین رایانه می‌مانند.

## پیش‌نیازها
- [uv](https://docs.astral.sh/uv/) (بک‌اند پایتون؛ خودش پایتون ۳.۱۲ را می‌گیرد)
- Node.js ۲۰ یا بالاتر (رابط کاربری، و سرورهای MCP که با `npx` اجرا می‌شوند)

## اجرا (توسعه)
```bash
uv sync
cd desktop
npm install        # Electron را هم دانلود می‌کند
npm run dev
```

## ساختار
```
src/vision/   main.py (FastAPI)، chat.py، providers.py، mcp_hub.py، approvals.py، memory.py،
              db.py (SQLite+FTS5)، secrets_store.py (Credential Manager)، catalog.py + data/mcp_catalog.json
desktop/      Electron + React
tests/        تست‌های بک‌اند (سرور MCP واقعی، استریم، تأیید، امنیت کلیدها)
scripts/      build_catalog.py، check_catalog.py، probe_catalog.py
```

## تست
```bash
uv run pytest                           # بک‌اند
cd desktop && npm test                  # رابط (بک‌اند واقعی + مدل ساختگی)
node check-i18n.mjs                     # کامل بودن متن‌های فارسی/انگلیسی
uv run python scripts/check_catalog.py  # وجود پکیج‌ها و نام متغیرهای کاتالوگ در npm/PyPI
uv run python scripts/probe_catalog.py  # هر سرور محلی کاتالوگ را واقعاً اجرا می‌کند و ابزارهایش را می‌شمارد
```
سرورهایی که کلید یا برنامه‌ی واقعی لازم دارند (دیتابیس‌ها، Docker، OAuth گوگل…) در probe با مقدار نمونه خطا می‌دهند؛ این طبیعی است.

## امنیت
بک‌اند فقط روی `127.0.0.1` با توکن تصادفی هر اجرا؛ کلیدها در Credential Manager سیستم (نه SQLite)؛
ابزارهایی که ممکن است چیزی را تغییر دهند پیش از اجرا تأیید می‌گیرند.

---

## English

Vision is a fully local desktop AI assistant: OpenAI-compatible model providers + MCP tools, dark UI with a turquoise accent, Persian and English.
It only goes online to talk to the model API and MCP servers; chats, memory and settings stay on this computer.

**Requirements:** [uv](https://docs.astral.sh/uv/) and Node.js 20+.

```bash
uv sync
cd desktop && npm install && npm run dev
```

**Tests:** `uv run pytest` · `cd desktop && npm test` · `node check-i18n.mjs` ·
`uv run python scripts/check_catalog.py` (packages/env names exist) · `uv run python scripts/probe_catalog.py` (actually starts every local catalog server).
Servers that need real credentials or apps (databases, Docker, Google OAuth…) fail the probe with placeholder values; that is expected.

**Security:** backend bound to `127.0.0.1` with a per-launch token; secrets live in the OS credential store, never in SQLite;
tools that may change something ask for your approval first.

**Next:** installer (PyInstaller backend + electron-builder).
