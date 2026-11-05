@echo off
cd /d "%~dp0.."
python3 tool_digest\digest_to_article.py >> tool_digest\article_run.log 2>&1
