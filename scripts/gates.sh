#!/usr/bin/env bash
# =============================================================================
# scripts/gates.sh — Disiplin Defteri kapı koşusu (backend)
# =============================================================================
# Test + lint + biçim + tip kontrolünü sırayla Docker konteynerinde çalıştırır.
# Herhangi biri kırmızı olursa betik durur (`set -e`).
# CI eşi: .github/workflows/kapilar.yml — adımlar değişirse ikisi birlikte değişir.
# =============================================================================
set -euo pipefail

# Windows Git Bash (MSYS) `/repo` gibi konteyner yollarını `C:/Program Files/Git/repo`
# biçimine çevirir; `-w /repo`, `-e PYTHONPATH=/repo` bozulur. Linux/CI'da etkisizdir.
export MSYS_NO_PATHCONV=1

# Betik hangi dizinden çağrılırsa çağrılsın depo kökünde koşar (aşağıdaki
# `frontend/node_modules` denetimi göreli yol kullanır).
cd "$(dirname "$0")/.."

# Backend `desktop` paketini import eder (app_password → desktop.backup); `desktop/`
# depo kökünde, konteynerde `/repo` altında durur. CI eşi: kapilar.yml backend işinin
# `PYTHONPATH: ${{ github.workspace }}` ortam değişkeni — bu yüzden backend
# konteynerindeki HER adıma `-e PYTHONPATH=/repo` verilir.
echo "== pytest =="
docker compose run --rm -e PYTHONPATH=/repo backend pytest

echo "== ruff check =="
docker compose run --rm -e PYTHONPATH=/repo backend ruff check .

echo "== ruff format --check =="
docker compose run --rm -e PYTHONPATH=/repo backend ruff format --check .

echo "== mypy =="
docker compose run --rm -e PYTHONPATH=/repo backend mypy .

# Masaüstü kabuğu (desktop/) depo kökünde durur ve backend paketlerini import eder;
# bu yüzden `-w /repo` ile koşulur, ruff/mypy yapılandırması backend'den verilir.
# AYRI koşu bilinçli: desktop testleri günlük (logging) yapılandırmasını değiştirdiği
# için backend testleriyle aynı pytest sürecinde koşarlarsa birbirlerini etkilerler.
echo "== desktop + packaging: pytest =="
docker compose run --rm -w /repo -e PYTHONPATH=/repo backend \
  pytest desktop/tests packaging/tests -q --no-cov

echo "== desktop: ruff =="
docker compose run --rm -w /repo -e PYTHONPATH=/repo backend sh -c \
  "ruff check desktop --config backend/pyproject.toml && ruff format --check desktop --config backend/pyproject.toml"

echo "== desktop: mypy =="
docker compose run --rm -w /repo -e PYTHONPATH=/repo -e MYPYPATH=/repo/backend backend \
  mypy desktop --config-file backend/pyproject.toml

echo "== packaging: ruff =="
docker compose run --rm -w /repo -e PYTHONPATH=/repo backend sh -c \
  "ruff check packaging --config backend/pyproject.toml && ruff format --check packaging --config backend/pyproject.toml"

echo "== packaging: mypy =="
docker compose run --rm -w /repo -e PYTHONPATH=/repo -e MYPYPATH=/repo/backend backend \
  mypy packaging --config-file backend/pyproject.toml

# node_modules yoksa `npx eslint`/`npx prettier` projenin kilitli sürümü yerine npm
# kayıt defterindeki en güncelini indirip koşar; sonuç CI'dan sapar (ör. prettier
# dosyaları farklı biçimler). CI eşi her koşuda `npm ci` yapar; yerelde her seferinde
# kurmamak için yalnız gerektiğinde kurulur: npm'in `node_modules/.package-lock.json`
# gizli kilidi yoksa (kurulum yok/yarım) ya da `package-lock.json` ondan yeniyse
# (git pull/checkout bağımlılık değiştirdi).
if [ ! -f frontend/node_modules/.package-lock.json ] \
  || [ frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]; then
  echo "== frontend: npm ci =="
  docker compose run --rm frontend npm ci
fi

echo "== frontend: typecheck =="
docker compose run --rm frontend npm run typecheck

echo "== frontend: eslint =="
docker compose run --rm frontend npx eslint src

echo "== frontend: prettier --check =="
docker compose run --rm frontend npx prettier --check src

echo "== frontend: vitest =="
docker compose run --rm frontend npm test -- --run

echo "== Tüm kapılar yeşil =="
