git remote add origin https://github.com/Sam-Khandnai/Vision_Desktop.git"""Generates src/vision/data/mcp_catalog.json (bilingual: fa + en).
Run: uv run python scripts/build_catalog.py
Then verify: uv run python scripts/check_catalog.py   (needs internet)
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "vision" / "data" / "mcp_catalog.json"
ENTRIES: list[dict] = []


def L(fa: str, en: str) -> dict:
    return {"fa": fa, "en": en}


def _inp(key, label, *, type="text", target="arg", name=None, template=None, required=True, default="", help=None):
    d = {"key": key, "label": L(*label), "type": type, "target": target, "required": required}
    if name:
        d["name"] = name
    if template:
        d["template"] = template
    if default:
        d["default"] = default
    if help:
        d["help"] = L(*help)
    return d


def folder(key="folder", label=("پوشه‌ی مجاز", "Allowed folder")):
    return _inp(key, label, type="path", help=("فقط به همین پوشه دسترسی داده می‌شود.", "Only this folder will be accessible."))


def file(key, label, help=None):
    return _inp(key, label, type="path", help=help)


def text(key, label, *, required=True, default="", help=None):
    return _inp(key, label, required=required, default=default, help=help)


def env(name, label, *, secret=True, required=True, default="", help=None):
    return _inp(name, label, type="secret" if secret else "text", target="env", name=name,
                required=required, default=default, help=help)


def bearer(label, required=True, help=None):
    return _inp("token", label, type="secret", target="header", name="Authorization",
                template="Bearer {{value}}", required=required, help=help)


# uvx otherwise picks the newest Python, which many MCP packages do not support yet -> pin per entry (default 3.12)


def _with(specs):
    return [x for spec in (specs or []) for x in ("--with", spec)]


def add(id, name, category, desc, *, kind, pkg=None, args=None, inputs=None, risk="low", url=None,
        note=None, command=None, docs=None, env_static=None, uv_with=None, uv_python="3.12"):
    e = {"id": id, "name": name, "category": category, "description": L(*desc), "risk": risk,
         "inputs": inputs or []}
    if note:
        e["note"] = L(*note)
    if kind == "npx":
        e.update(transport="stdio", command="npx", args=["-y", pkg, *(args or [])], package=pkg,
                 registry="npm", requires="node", docs=docs or f"https://www.npmjs.com/package/{pkg}")
    elif kind == "uvx":
        base = pkg.split("@")[0]
        e.update(transport="stdio", command="uvx", args=["--python", uv_python, *_with(uv_with), pkg, *(args or [])], package=base,
                 registry="pypi", requires="uv", docs=docs or f"https://pypi.org/project/{base}/")
    elif kind == "uvx-from":
        base = pkg.split("@")[0]
        e.update(transport="stdio", command="uvx", args=["--python", uv_python, *_with(uv_with), "--from", pkg, command, *(args or [])],
                 package=base, registry="pypi", requires="uv", docs=docs or f"https://pypi.org/project/{base}/")
    elif kind == "remote":
        e.update(transport="streamable_http", url=url, package="", registry="", requires="", docs=docs or url)
    if env_static:
        e["env_static"] = env_static
    ENTRIES.append(e)


# =============================== Files & Docs ===============================
add("filesystem", "Filesystem", "files", ("خواندن، جستجو و ویرایش فایل‌ها در یک پوشه‌ی مشخص.", "Read, search and edit files inside one folder."),
    kind="npx", pkg="@modelcontextprotocol/server-filesystem", args=["{{folder}}"], inputs=[folder()], risk="high",
    docs="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem")
add("markitdown", "MarkItDown", "files", ("تبدیل PDF، Word، Excel، PowerPoint و تصویر به متن Markdown.", "Convert PDF, Word, Excel, PowerPoint and images to Markdown text."),
    kind="uvx", pkg="markitdown-mcp")
add("pandoc", "Pandoc", "files", ("تبدیل فرمت اسناد (Markdown، DOCX، HTML، PDF و…).", "Convert documents between formats (Markdown, DOCX, HTML, PDF…)."),
    kind="uvx", pkg="mcp-pandoc", risk="medium",
    note=("برای خروجی PDF باید Pandoc روی سیستم نصب باشد.", "Pandoc must be installed on your system for PDF output."))
add("excel", "Excel", "files", ("خواندن و نوشتن فایل‌های Excel بدون نیاز به نصب Office.", "Read and write Excel files without Office installed."),
    kind="npx", pkg="@negokaz/excel-mcp-server", risk="medium")
add("word", "Word Documents", "files", ("ساخت و ویرایش فایل‌های Word (docx).", "Create and edit Word (docx) files."),
    kind="uvx-from", pkg="office-word-mcp-server", command="word_mcp_server", risk="medium", uv_with=["mcp<2"])
add("powerpoint", "PowerPoint", "files", ("ساخت و ویرایش ارائه‌های PowerPoint.", "Create and edit PowerPoint presentations."),
    kind="uvx-from", pkg="office-powerpoint-mcp-server", command="ppt_mcp_server", risk="medium", uv_with=["mcp<2"])
add("pdf-reader", "PDF Reader", "files", ("استخراج متن و اطلاعات صفحه‌ها از فایل‌های PDF.", "Extract text and page details from PDF files."),
    kind="npx", pkg="@sylphlab/pdf-reader-mcp")
add("obsidian", "Obsidian", "files", ("جستجو و ویرایش یادداشت‌های Obsidian.", "Search and edit your Obsidian notes."),
    kind="uvx", pkg="mcp-obsidian", risk="medium",
    inputs=[env("OBSIDIAN_API_KEY", ("کلید API افزونه", "Plugin API key")),
            env("OBSIDIAN_HOST", ("آدرس", "Host"), secret=False, required=False, default="127.0.0.1")],
    note=("افزونه‌ی «Local REST API» باید در Obsidian نصب و روشن باشد.", "The “Local REST API” plugin must be installed and enabled in Obsidian."))
add("ripgrep", "Ripgrep", "files", ("جستجوی سریع متن داخل فایل‌ها و پوشه‌ها.", "Fast text search across files and folders."),
    kind="npx", pkg="mcp-ripgrep", note=("ابزار ripgrep باید روی سیستم نصب باشد.", "ripgrep must be installed on your system."))

# ============================== Web & Search ================================
add("fetch", "Fetch", "web", ("دریافت یک صفحه‌ی وب و تبدیل آن به متن خوانا.", "Fetch a web page and turn it into readable text."),
    kind="uvx", pkg="mcp-server-fetch", docs="https://github.com/modelcontextprotocol/servers/tree/main/src/fetch")
add("duckduckgo", "DuckDuckGo Search", "web", ("جستجوی وب بدون نیاز به کلید API.", "Web search with no API key needed."),
    kind="uvx", pkg="duckduckgo-mcp-server")
add("brave-search", "Brave Search", "web", ("جستجوی وب و اخبار با Brave.", "Web and news search with Brave."),
    kind="npx", pkg="@brave/brave-search-mcp-server", inputs=[env("BRAVE_API_KEY", ("کلید API بریو", "Brave API key"))])
add("tavily", "Tavily", "web", ("جستجو و استخراج محتوا، ساخته‌شده برای عامل‌های هوش مصنوعی.", "Search and content extraction built for AI agents."),
    kind="npx", pkg="tavily-mcp", inputs=[env("TAVILY_API_KEY", ("کلید API تاویلی", "Tavily API key"))])
add("exa", "Exa", "web", ("جستجوی معنایی وب و پیدا کردن منابع مشابه.", "Semantic web search and finding similar sources."),
    kind="remote", url="https://mcp.exa.ai/mcp", inputs=[bearer(("کلید API اکسا", "Exa API key"), required=False)],
    note=("بدون کلید هم با محدودیت کار می‌کند؛ با کلید محدودیت بیشتر می‌شود.", "Works without a key with rate limits; a key raises the limits."),
    docs="https://github.com/exa-labs/exa-mcp-server")
add("perplexity", "Perplexity", "web", ("جستجو و پاسخ‌های مستند با Perplexity.", "Search and cited answers with Perplexity."),
    kind="npx", pkg="@perplexity-ai/mcp-server", inputs=[env("PERPLEXITY_API_KEY", ("کلید API پرپلکسیتی", "Perplexity API key"))])
add("kagi", "Kagi Search", "web", ("جستجوی بدون تبلیغ با Kagi و خلاصه‌سازی صفحه‌ها.", "Ad-free search and page summaries with Kagi."),
    kind="uvx", pkg="kagimcp", inputs=[env("KAGI_API_KEY", ("کلید API کاگی", "Kagi API key"))])
add("searxng", "SearXNG", "web", ("جستجو از طریق نمونه‌ی SearXNG خودت (حریم خصوصی بیشتر).", "Search through your own SearXNG instance (more privacy)."),
    kind="npx", pkg="mcp-searxng", inputs=[env("SEARXNG_URL", ("آدرس SearXNG", "SearXNG URL"), secret=False, default="http://localhost:8080")])
add("firecrawl", "Firecrawl", "web", ("خزیدن در سایت‌ها و استخراج داده‌ی ساختاریافته.", "Crawl sites and extract structured data."),
    kind="npx", pkg="firecrawl-mcp", inputs=[env("FIRECRAWL_API_KEY", ("کلید API فایرکرال", "Firecrawl API key"))])
add("playwright", "Playwright", "web", ("کنترل مرورگر: باز کردن صفحه، کلیک، پر کردن فرم و عکس‌برداری.", "Control a browser: open pages, click, fill forms, take screenshots."),
    kind="npx", pkg="@playwright/mcp", risk="medium", note=("اولین اجرا ممکن است مرورگر را دانلود کند.", "The first run may download a browser."))
add("playwright-ea", "Playwright (ExecuteAutomation)", "web", ("خودکارسازی مرورگر و تست وب با Playwright.", "Browser automation and web testing with Playwright."),
    kind="npx", pkg="@executeautomation/playwright-mcp-server", risk="medium")
add("browserbase", "Browserbase", "web", ("مرورگر ابری برای خودکارسازی صفحه‌های وب.", "Cloud browser for automating web pages."),
    kind="npx", pkg="@browserbasehq/mcp-server-browserbase", risk="medium",
    inputs=[env("BROWSERBASE_API_KEY", ("کلید API", "API key")), env("BROWSERBASE_PROJECT_ID", ("شناسه‌ی پروژه", "Project ID"), secret=False)])
add("chrome-devtools", "Chrome DevTools", "web", ("بررسی و عیب‌یابی صفحه‌های وب با ابزارهای توسعه‌دهنده‌ی کروم.", "Inspect and debug web pages with Chrome DevTools."),
    kind="npx", pkg="chrome-devtools-mcp", risk="medium", note=("نیاز به Google Chrome نصب‌شده دارد.", "Requires Google Chrome to be installed."))
add("apify", "Apify", "web", ("اجرای هزاران ابزار آماده‌ی استخراج داده از سایت‌ها و شبکه‌های اجتماعی.", "Run thousands of ready-made scrapers for sites and social networks."),
    kind="npx", pkg="@apify/actors-mcp-server", risk="medium", inputs=[env("APIFY_TOKEN", ("توکن Apify", "Apify token"))])
add("youtube-transcript", "YouTube Transcript", "web", ("گرفتن متن زیرنویس ویدیوهای یوتیوب.", "Get the transcript of YouTube videos."),
    kind="npx", pkg="@kimtaeyoon83/mcp-server-youtube-transcript")
add("yt-dlp", "yt-dlp", "web", ("دانلود ویدیو و زیرنویس از یوتیوب و سایت‌های دیگر.", "Download videos and subtitles from YouTube and other sites."),
    kind="npx", pkg="@kevinwatt/yt-dlp-mcp", risk="medium", note=("ابزار yt-dlp باید روی سیستم نصب باشد.", "yt-dlp must be installed on your system."))
add("wikipedia", "Wikipedia", "web", ("جستجو و خواندن مقاله‌های ویکی‌پدیا.", "Search and read Wikipedia articles."), kind="uvx", pkg="wikipedia-mcp")
add("arxiv", "arXiv", "web", ("جستجو و دانلود مقاله‌های علمی از arXiv.", "Search and download scientific papers from arXiv."),
    kind="uvx", pkg="arxiv-mcp-server", args=["--storage-path", "{{folder}}"],
    inputs=[folder("folder", ("پوشه‌ی ذخیره‌ی مقاله‌ها", "Folder to store papers"))])
add("paper-search", "Paper Search", "web", ("جستجوی مقاله در arXiv، PubMed، bioRxiv و منابع دیگر.", "Search papers across arXiv, PubMed, bioRxiv and more."),
    kind="uvx", pkg="paper-search-mcp", uv_with=["mcp<2"])
add("weather", "Weather", "web", ("وضعیت و پیش‌بینی آب‌وهوا بدون نیاز به کلید.", "Current weather and forecasts, no key needed."),
    kind="uvx-from", pkg="mcp-weather-server", command="mcp_weather_server", uv_with=["mcp<2"])
add("google-maps", "Google Maps", "web", ("جستجوی مکان، مسیریابی و فاصله.", "Place search, directions and distances."),
    kind="npx", pkg="@modelcontextprotocol/server-google-maps", inputs=[env("GOOGLE_MAPS_API_KEY", ("کلید API نقشه‌ی گوگل", "Google Maps API key"))],
    note=("این پکیج بایگانی شده است.", "This package is archived."))
add("deepwiki", "DeepWiki", "web", ("پرسش درباره‌ی مستندات و ساختار پروژه‌های GitHub.", "Ask about the docs and structure of GitHub projects."),
    kind="remote", url="https://mcp.deepwiki.com/mcp")
add("ms-learn", "Microsoft Learn", "web", ("جستجو در مستندات رسمی مایکروسافت و Azure.", "Search the official Microsoft and Azure docs."),
    kind="remote", url="https://learn.microsoft.com/api/mcp")
add("cloudflare-docs", "Cloudflare Docs", "web", ("جستجو در مستندات Cloudflare.", "Search the Cloudflare docs."),
    kind="remote", url="https://docs.mcp.cloudflare.com/mcp")
add("grep-app", "Grep (code search)", "web", ("جستجوی کد در میلیون‌ها مخزن عمومی GitHub.", "Search code across millions of public GitHub repositories."),
    kind="remote", url="https://mcp.grep.app")

# ============================== Development =================================
add("git", "Git", "dev", ("مشاهده‌ی وضعیت، تفاوت‌ها و تاریخچه‌ی یک مخزن Git و ثبت commit.", "View status, diffs and history of a Git repo, and make commits."),
    kind="uvx", pkg="mcp-server-git", args=["--repository", "{{repo}}"],
    inputs=[folder("repo", ("پوشه‌ی مخزن Git", "Git repository folder"))], risk="medium",
    docs="https://github.com/modelcontextprotocol/servers/tree/main/src/git")
add("github", "GitHub", "dev", ("کار با مخزن‌ها، issueها و pull requestها در GitHub.", "Work with repos, issues and pull requests on GitHub."),
    kind="remote", url="https://api.githubcopilot.com/mcp/", inputs=[bearer(("توکن شخصی GitHub (PAT)", "GitHub personal access token (PAT)"))],
    risk="high", docs="https://github.com/github/github-mcp-server")
add("gitlab", "GitLab", "dev", ("کار با پروژه‌ها، issueها و merge requestها در GitLab.", "Work with projects, issues and merge requests on GitLab."),
    kind="npx", pkg="@zereight/mcp-gitlab", risk="high",
    inputs=[env("GITLAB_PERSONAL_ACCESS_TOKEN", ("توکن شخصی GitLab", "GitLab personal access token")),
            env("GITLAB_API_URL", ("آدرس API", "API URL"), secret=False, required=False, default="https://gitlab.com/api/v4")])
add("context7", "Context7", "dev", ("مستندات به‌روز و نمونه‌کد کتابخانه‌ها برای هر نسخه.", "Up-to-date docs and code samples for libraries."),
    kind="npx", pkg="@upstash/context7-mcp")
add("semgrep", "Semgrep", "dev", ("اسکن امنیتی و کیفیت کد با Semgrep.", "Scan code for security and quality issues with Semgrep."),
    kind="uvx", pkg="semgrep-mcp", uv_with=["mcp<2", "pydantic<2.12"])
add("sentry", "Sentry", "dev", ("بررسی خطاها و issueهای پروژه در Sentry.", "Inspect errors and issues of your Sentry projects."),
    kind="npx", pkg="@sentry/mcp-server", risk="medium", inputs=[env("SENTRY_ACCESS_TOKEN", ("توکن دسترسی Sentry", "Sentry access token"))])
add("atlassian", "Jira & Confluence", "dev", ("جستجو و ویرایش issueهای Jira و صفحه‌های Confluence.", "Search and edit Jira issues and Confluence pages."),
    kind="uvx", pkg="mcp-atlassian", risk="medium",
    inputs=[env("JIRA_URL", ("آدرس Jira", "Jira URL"), secret=False, required=False, help=("مثال: https://شرکت.atlassian.net", "Example: https://your-company.atlassian.net")),
            env("JIRA_USERNAME", ("ایمیل Jira", "Jira email"), secret=False, required=False),
            env("JIRA_API_TOKEN", ("توکن API جیرا", "Jira API token"), required=False),
            env("CONFLUENCE_URL", ("آدرس Confluence", "Confluence URL"), secret=False, required=False),
            env("CONFLUENCE_USERNAME", ("ایمیل Confluence", "Confluence email"), secret=False, required=False),
            env("CONFLUENCE_API_TOKEN", ("توکن API کانفلوئنس", "Confluence API token"), required=False)],
    note=("هر کدام از Jira یا Confluence را که استفاده می‌کنی پر کن.", "Fill in whichever of Jira or Confluence you use."))
add("linear", "Linear", "dev", ("مدیریت issueها و پروژه‌ها در Linear.", "Manage issues and projects in Linear."),
    kind="remote", url="https://mcp.linear.app/mcp", inputs=[bearer(("کلید API لینیر", "Linear API key"))], risk="medium", docs="https://linear.app/docs/mcp")
add("postman", "Postman", "dev", ("کار با collectionها و محیط‌های Postman.", "Work with Postman collections and environments."),
    kind="npx", pkg="@postman/postman-mcp-server", risk="medium", inputs=[env("POSTMAN_API_KEY", ("کلید API پستمن", "Postman API key"))])
add("code-runner", "Code Runner", "dev", ("اجرای قطعه‌کد در زبان‌های مختلف روی سیستم تو.", "Run code snippets in many languages on your machine."),
    kind="npx", pkg="mcp-server-code-runner", risk="high", note=("کد روی رایانه‌ی خودت اجرا می‌شود؛ هر بار تأیید بگیر.", "Code runs on your own computer; keep approval on."))
add("e2b", "E2B Sandbox", "dev", ("اجرای امن کد در سندباکس ابری E2B.", "Run code safely in an E2B cloud sandbox."),
    kind="npx", pkg="@e2b/mcp-server", risk="medium", inputs=[env("E2B_API_KEY", ("کلید API E2B", "E2B API key"))])
add("figma-api", "Figma (API)", "dev", ("خواندن فایل‌های Figma از طریق API برای تبدیل به کد.", "Read Figma files through the API and turn designs into code."),
    kind="npx", pkg="figma-developer-mcp", args=["--stdio"], risk="medium", inputs=[env("FIGMA_API_KEY", ("توکن دسترسی Figma", "Figma access token"))])
add("huggingface", "Hugging Face", "dev", ("جستجوی مدل‌ها، دیتاست‌ها و مقاله‌ها در Hugging Face.", "Search models, datasets and papers on Hugging Face."),
    kind="remote", url="https://huggingface.co/mcp", inputs=[bearer(("توکن Hugging Face", "Hugging Face token"), required=False)], risk="medium",
    docs="https://huggingface.co/settings/mcp")
add("n8n", "n8n Nodes", "dev", ("مستندات و اطلاعات نودهای n8n برای ساخت workflow.", "Docs and details of n8n nodes for building workflows."),
    kind="npx", pkg="n8n-mcp", env_static={"MCP_MODE": "stdio", "LOG_LEVEL": "error", "DISABLE_CONSOLE_OUTPUT": "true"})
add("antv-chart", "AntV Charts", "dev", ("ساخت نمودارهای زیبا (ستونی، خطی، دایره‌ای و…).", "Generate charts (bar, line, pie…)."),
    kind="npx", pkg="@antv/mcp-server-chart",
    note=("داده‌ی نمودار برای ساخته‌شدن به سرویس AntV فرستاده می‌شود.", "Chart data is sent to the AntV service to render."))
add("aws-docs", "AWS Documentation", "dev", ("جستجو و خواندن مستندات رسمی AWS.", "Search and read the official AWS docs."),
    kind="uvx", pkg="awslabs.aws-documentation-mcp-server@latest")

# ========================== Cloud & Infrastructure ==========================
add("docker", "Docker", "cloud", ("مدیریت کانتینرها، ایمیج‌ها و شبکه‌های Docker.", "Manage Docker containers, images and networks."),
    kind="uvx-from", pkg="mcp-server-docker", command="mcp-server-docker", risk="high",
    note=("Docker Desktop باید در حال اجرا باشد.", "Docker Desktop must be running."))
add("azure", "Azure", "cloud", ("مدیریت منابع و سرویس‌های Azure.", "Manage Azure resources and services."),
    kind="npx", pkg="@azure/mcp", args=["server", "start"], risk="high",
    note=("ابتدا با Azure CLI وارد حساب شو (az login).", "Sign in first with the Azure CLI (az login)."))

# ============================ Data & Databases ==============================
add("sqlite", "SQLite", "data", ("اجرای کوئری روی فایل پایگاه‌داده‌ی SQLite.", "Run queries on a SQLite database file."),
    kind="uvx", pkg="mcp-server-sqlite", args=["--db-path", "{{file}}"],
    inputs=[file("file", ("مسیر فایل SQLite", "SQLite file path"))], risk="medium")
add("postgres", "PostgreSQL", "data", ("بررسی ساختار و اجرای کوئری روی PostgreSQL (پیش‌فرض: فقط‌خواندنی).", "Inspect schema and query PostgreSQL (read-only by default)."),
    kind="uvx", pkg="postgres-mcp", args=["--access-mode=restricted"], risk="medium",
    inputs=[env("DATABASE_URI", ("آدرس اتصال", "Connection URI"), help=("مثال: postgresql://user:pass@localhost:5432/db", "Example: postgresql://user:pass@localhost:5432/db"))])
add("mysql", "MySQL", "data", ("کوئری روی پایگاه‌داده‌ی MySQL.", "Query a MySQL database."),
    kind="npx", pkg="@benborla29/mcp-server-mysql", risk="high",
    inputs=[env("MYSQL_HOST", ("میزبان", "Host"), secret=False, default="127.0.0.1"), env("MYSQL_PORT", ("پورت", "Port"), secret=False, default="3306"),
            env("MYSQL_USER", ("نام کاربری", "Username"), secret=False), env("MYSQL_PASS", ("گذرواژه", "Password")),
            env("MYSQL_DB", ("نام پایگاه‌داده", "Database name"), secret=False)])
add("mongodb", "MongoDB", "data", ("کار با مجموعه‌ها و اسناد MongoDB (فقط‌خواندنی).", "Work with MongoDB collections and documents (read-only)."),
    kind="npx", pkg="mongodb-mcp-server", args=["--readOnly"], risk="medium",
    inputs=[env("MDB_MCP_CONNECTION_STRING", ("رشته‌ی اتصال", "Connection string"))])
add("redis", "Redis", "data", ("خواندن و نوشتن داده در Redis.", "Read and write data in Redis."),
    kind="uvx-from", pkg="redis-mcp-server@latest", command="redis-mcp-server", risk="high",
    inputs=[env("REDIS_HOST", ("میزبان", "Host"), secret=False, default="127.0.0.1"), env("REDIS_PORT", ("پورت", "Port"), secret=False, default="6379"),
            env("REDIS_PWD", ("گذرواژه", "Password"), required=False)])
add("duckdb", "DuckDB / MotherDuck", "data", ("تحلیل داده با SQL روی فایل‌های DuckDB، CSV و Parquet (فقط‌خواندنی).", "Analyze data with SQL over DuckDB, CSV and Parquet files (read-only)."),
    kind="uvx", pkg="mcp-server-motherduck", args=["--db-path", "{{file}}"], risk="medium",
    inputs=[file("file", ("مسیر فایل DuckDB", "DuckDB file path"), help=("برای دیتابیس موقت در حافظه بنویس: :memory:", "For a temporary in-memory database type: :memory:"))])
add("clickhouse", "ClickHouse", "data", ("کوئری تحلیلی روی ClickHouse.", "Analytical queries on ClickHouse."),
    kind="uvx", pkg="mcp-clickhouse", risk="medium",
    inputs=[env("CLICKHOUSE_HOST", ("میزبان", "Host"), secret=False), env("CLICKHOUSE_USER", ("نام کاربری", "Username"), secret=False),
            env("CLICKHOUSE_PASSWORD", ("گذرواژه", "Password"))])
add("neo4j", "Neo4j", "data", ("کوئری Cypher روی پایگاه‌داده‌ی گراف Neo4j.", "Run Cypher queries on a Neo4j graph database."),
    kind="uvx", pkg="mcp-neo4j-cypher", risk="medium",
    inputs=[env("NEO4J_URI", ("آدرس", "URI"), secret=False, default="bolt://localhost:7687"), env("NEO4J_USERNAME", ("نام کاربری", "Username"), secret=False, default="neo4j"),
            env("NEO4J_PASSWORD", ("گذرواژه", "Password"))])
add("qdrant", "Qdrant", "data", ("ذخیره و جستجوی معنایی در پایگاه‌داده‌ی برداری Qdrant.", "Store and semantically search in the Qdrant vector database."),
    kind="uvx", pkg="mcp-server-qdrant", risk="medium",
    inputs=[env("QDRANT_LOCAL_PATH", ("پوشه‌ی ذخیره‌ی محلی", "Local storage folder"), secret=False),
            env("COLLECTION_NAME", ("نام مجموعه", "Collection name"), secret=False, default="vision-memory")])
add("chroma", "Chroma", "data", ("پایگاه‌داده‌ی برداری محلی Chroma برای جستجوی معنایی.", "Local Chroma vector database for semantic search."),
    kind="uvx", pkg="chroma-mcp", uv_with=["mcp<2", "pydantic<2.12"], args=["--client-type", "persistent", "--data-dir", "{{folder}}"],
    inputs=[folder("folder", ("پوشه‌ی داده", "Data folder"))], risk="medium")
add("pinecone", "Pinecone", "data", ("کار با ایندکس‌های برداری Pinecone و مستندات آن.", "Work with Pinecone vector indexes and docs."),
    kind="npx", pkg="@pinecone-database/mcp", risk="medium", inputs=[env("PINECONE_API_KEY", ("کلید API پاین‌کون", "Pinecone API key"))])
add("airtable", "Airtable", "data", ("خواندن و ویرایش جدول‌های Airtable.", "Read and edit Airtable tables."),
    kind="npx", pkg="airtable-mcp-server", risk="medium", inputs=[env("AIRTABLE_API_KEY", ("توکن شخصی Airtable", "Airtable personal access token"))])

# ============================== Productivity ================================
add("notion", "Notion", "productivity", ("جستجو و ویرایش صفحه‌ها و دیتابیس‌های Notion.", "Search and edit Notion pages and databases."),
    kind="npx", pkg="@notionhq/notion-mcp-server", risk="medium", inputs=[env("NOTION_TOKEN", ("توکن Integration", "Integration token"))],
    note=("صفحه‌ها را باید با Integration به اشتراک بگذاری.", "You must share pages with the integration."))
add("todoist", "Todoist", "productivity", ("مدیریت کارها و پروژه‌ها در Todoist.", "Manage tasks and projects in Todoist."),
    kind="npx", pkg="@abhiz123/todoist-mcp-server", risk="medium", inputs=[env("TODOIST_API_TOKEN", ("توکن API", "API token"))])
add("trello", "Trello", "productivity", ("مدیریت بردها، لیست‌ها و کارت‌های Trello.", "Manage Trello boards, lists and cards."),
    kind="npx", pkg="@delorenj/mcp-server-trello", risk="medium",
    inputs=[env("TRELLO_API_KEY", ("کلید API", "API key")), env("TRELLO_TOKEN", ("توکن", "Token"))])
add("asana", "Asana", "productivity", ("مدیریت پروژه‌ها و کارها در Asana.", "Manage projects and tasks in Asana."),
    kind="npx", pkg="@roychri/mcp-server-asana", risk="medium", inputs=[env("ASANA_ACCESS_TOKEN", ("توکن دسترسی شخصی", "Personal access token"))])
add("clickup", "ClickUp", "productivity", ("مدیریت کارها و فضاهای کاری در ClickUp.", "Manage tasks and workspaces in ClickUp."),
    kind="npx", pkg="@taazkareem/clickup-mcp-server", risk="medium",
    inputs=[env("CLICKUP_API_KEY", ("کلید API", "API key")), env("CLICKUP_TEAM_ID", ("شناسه‌ی Workspace", "Workspace ID"), secret=False)])
add("google-calendar", "Google Calendar", "productivity", ("مشاهده و ساخت رویداد در تقویم گوگل.", "View and create events in Google Calendar."),
    kind="npx", pkg="@cocal/google-calendar-mcp", risk="medium",
    inputs=[env("GOOGLE_OAUTH_CREDENTIALS", ("مسیر فایل credentials.json", "Path to credentials.json"), secret=False)],
    note=("باید یک OAuth client در Google Cloud بسازی (نوع Desktop) و فایل JSON آن را اینجا بدهی.", "Create an OAuth client (Desktop type) in Google Cloud and give its JSON file here."))
add("google-workspace", "Google Workspace", "productivity", ("Gmail، Drive، Docs، Sheets، Calendar و بیشتر در یک سرور.", "Gmail, Drive, Docs, Sheets, Calendar and more in one server."),
    kind="uvx", pkg="workspace-mcp", risk="high",
    inputs=[env("GOOGLE_OAUTH_CLIENT_ID", ("شناسه‌ی OAuth Client", "OAuth client ID"), secret=False), env("GOOGLE_OAUTH_CLIENT_SECRET", ("رمز OAuth Client", "OAuth client secret"))],
    note=("اولین بار باید در مرورگر وارد حساب گوگل شوی.", "The first time you must sign in to Google in your browser."))
add("time", "Time", "productivity", ("ساعت و تاریخ دقیق و تبدیل منطقه‌ی زمانی.", "Accurate date and time, and timezone conversion."),
    kind="uvx", pkg="mcp-server-time", docs="https://github.com/modelcontextprotocol/servers/tree/main/src/time")
add("calculator", "Calculator", "productivity", ("محاسبات دقیق ریاضی.", "Precise math calculations."), kind="uvx", pkg="mcp-server-calculator")

# ============================== Communication ===============================
add("slack", "Slack", "comms", ("خواندن کانال‌ها و ارسال پیام در Slack.", "Read channels and send messages in Slack."),
    kind="npx", pkg="@zencoderai/slack-mcp-server", risk="medium",
    inputs=[env("SLACK_BOT_TOKEN", ("توکن ربات (xoxb-…)", "Bot token (xoxb-…)")), env("SLACK_TEAM_ID", ("شناسه‌ی Workspace", "Workspace ID"), secret=False)])
add("discord", "Discord", "comms", ("خواندن و ارسال پیام در سرورهای Discord.", "Read and send messages in Discord servers."),
    kind="npx", pkg="mcp-discord", risk="medium", inputs=[env("DISCORD_TOKEN", ("توکن ربات", "Bot token"))])
add("gmail", "Gmail", "comms", ("جستجو، خواندن و ارسال ایمیل در Gmail.", "Search, read and send email in Gmail."),
    kind="npx", pkg="@gongrzhe/server-gmail-autoauth-mcp", risk="high",
    note=("اولین بار باید طبق راهنمای پکیج وارد حساب گوگل شوی (OAuth).", "On first use sign in to Google following the package guide (OAuth)."))
add("resend", "Resend (email)", "comms", ("ارسال ایمیل با سرویس Resend.", "Send email with the Resend service."),
    kind="npx", pkg="resend-mcp", risk="medium", inputs=[env("RESEND_API_KEY", ("کلید API رسند", "Resend API key"))])

# ============================ Business & Finance ============================
add("stripe", "Stripe", "business", ("مشاهده‌ی مشتری‌ها، پرداخت‌ها و ساخت لینک پرداخت در Stripe.", "View customers, payments and create payment links in Stripe."),
    kind="remote", url="https://mcp.stripe.com", inputs=[bearer(("کلید محدود Stripe (rk_…)", "Stripe restricted key (rk_…)"), help=("از کلید محدودشده استفاده کن، نه کلید اصلی.", "Use a restricted key, not your main secret key."))],
    risk="high", docs="https://docs.stripe.com/mcp")
add("paypal", "PayPal", "business", ("کار با فاکتور، پرداخت و سفارش‌ها در PayPal.", "Work with invoices, payments and orders in PayPal."),
    kind="npx", pkg="@paypal/mcp", args=["--tools=all"], risk="high",
    inputs=[env("PAYPAL_ACCESS_TOKEN", ("توکن دسترسی", "Access token")), env("PAYPAL_ENVIRONMENT", ("محیط (SANDBOX یا PRODUCTION)", "Environment (SANDBOX or PRODUCTION)"), secret=False, default="SANDBOX")])
add("hubspot", "HubSpot", "business", ("مدیریت مخاطبان، معامله‌ها و شرکت‌ها در HubSpot.", "Manage contacts, deals and companies in HubSpot."),
    kind="npx", pkg="@hubspot/mcp-server", risk="medium", inputs=[env("PRIVATE_APP_ACCESS_TOKEN", ("توکن Private App", "Private app token"))])
add("coingecko", "CoinGecko", "business", ("قیمت و اطلاعات بازار ارزهای دیجیتال.", "Crypto prices and market data."),
    kind="npx", pkg="@coingecko/coingecko-mcp",
    inputs=[env("COINGECKO_PRO_API_KEY", ("کلید API نسخه‌ی Pro", "Pro API key"), required=False)],
    note=("بدون کلید هم با محدودیت کار می‌کند.", "Works with limits even without a key."))

# ============================== AI & Memory =================================
add("memory", "Knowledge Graph Memory", "ai", ("حافظه‌ی گراف دانش برای نگهداری موجودیت‌ها و رابطه‌ها.", "Knowledge-graph memory for entities and relations."),
    kind="npx", pkg="@modelcontextprotocol/server-memory", docs="https://github.com/modelcontextprotocol/servers/tree/main/src/memory")
add("basic-memory", "Basic Memory", "ai", ("پایگاه دانش محلی روی فایل‌های Markdown که بین گفتگوها می‌ماند.", "Local knowledge base in Markdown files that persists across chats."),
    kind="uvx", pkg="basic-memory", args=["mcp"])
add("sequential-thinking", "Sequential Thinking", "ai", ("کمک به حل مسئله‌های پیچیده با تفکر مرحله‌به‌مرحله.", "Step-by-step thinking for complex problems."),
    kind="npx", pkg="@modelcontextprotocol/server-sequential-thinking", docs="https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking")

# ============================= Design & Media ===============================
add("figma", "Figma (Dev Mode)", "creative", ("خواندن طراحی‌های Figma برای تبدیل به کد.", "Read Figma designs to turn them into code."),
    kind="remote", url="http://127.0.0.1:3845/mcp",
    note=("برنامه‌ی دسکتاپ Figma باید باز باشد و Dev Mode MCP Server در آن روشن شود.", "The Figma desktop app must be open with the Dev Mode MCP Server turned on."),
    docs="https://help.figma.com/hc/en-us/articles/32132100833559")
add("blender", "Blender", "creative", ("ساخت و ویرایش صحنه‌های سه‌بعدی در Blender.", "Create and edit 3D scenes in Blender."),
    kind="uvx", pkg="blender-mcp", risk="medium", note=("افزونه‌ی BlenderMCP باید در Blender نصب و متصل باشد.", "The BlenderMCP add-on must be installed and connected in Blender."))
add("elevenlabs", "ElevenLabs", "creative", ("تبدیل متن به گفتار و ساخت صدا با ElevenLabs.", "Text-to-speech and voice generation with ElevenLabs."),
    kind="uvx", pkg="elevenlabs-mcp", risk="medium", inputs=[env("ELEVENLABS_API_KEY", ("کلید API", "API key"))],
    note=("استفاده از اعتبار حساب ElevenLabs را مصرف می‌کند.", "Uses your ElevenLabs account credits."))

# ============================ System & Automation ===========================
add("desktop-commander", "Desktop Commander", "system", ("اجرای دستور ترمینال و مدیریت فایل‌ها و پردازش‌ها روی سیستم.", "Run terminal commands and manage files and processes on your system."),
    kind="npx", pkg="@wonderwhy-er/desktop-commander", risk="high", note=("دسترسی گسترده به سیستم دارد؛ فقط در صورت نیاز فعالش کن.", "Has broad access to your system; enable it only when needed."))
add("commands", "Shell Commands", "system", ("اجرای دستورهای شل روی رایانه.", "Run shell commands on your computer."),
    kind="npx", pkg="mcp-server-commands", risk="high", note=("هر دستور را قبل از اجرا بررسی کن.", "Review every command before it runs."))
add("windows-mcp", "Windows Control", "system", ("کنترل ویندوز: باز کردن برنامه‌ها، کلیک، تایپ و عکس از صفحه.", "Control Windows: open apps, click, type and take screenshots."),
    kind="uvx", pkg="windows-mcp", risk="high", note=("فقط برای ویندوز است و کنترل کامل صفحه می‌دهد؛ تأیید را روشن نگه دار.", "Windows only and gives full control of the screen; keep approval on."))
add("home-assistant", "Home Assistant", "system", ("کنترل خانه‌ی هوشمند با Home Assistant.", "Control your smart home with Home Assistant."),
    kind="uvx", pkg="hass-mcp", risk="medium", uv_python="3.13",
    inputs=[env("HA_URL", ("آدرس Home Assistant", "Home Assistant URL"), secret=False, default="http://homeassistant.local:8123"), env("HA_TOKEN", ("توکن دسترسی بلندمدت", "Long-lived access token"))])

CATEGORIES = {
    "files": L("فایل و سند", "Files & Docs"),
    "web": L("وب و جستجو", "Web & Search"),
    "dev": L("برنامه‌نویسی", "Development"),
    "cloud": L("ابر و زیرساخت", "Cloud & Infrastructure"),
    "data": L("داده و دیتابیس", "Data & Databases"),
    "productivity": L("بهره‌وری", "Productivity"),
    "comms": L("ارتباطات", "Communication"),
    "business": L("کسب‌وکار و مالی", "Business & Finance"),
    "ai": L("هوش و حافظه", "AI & Memory"),
    "creative": L("طراحی و رسانه", "Design & Media"),
    "system": L("سیستم و خودکارسازی", "System & Automation"),
}

if __name__ == "__main__":
    ids = [e["id"] for e in ENTRIES]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert {e["category"] for e in ENTRIES} <= set(CATEGORIES)
    OUT.write_text(json.dumps({"categories": CATEGORIES, "servers": ENTRIES}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(ENTRIES)} entries -> {OUT}")
