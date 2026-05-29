#!/bin/bash
# EC2 배포 스크립트 — SSM으로 root 권한으로 실행됨
set -e

install_docker() {
  echo "▶ Docker 공식 저장소 설치 시작..."
  apt-get update -y -qq
  apt-get install -y -qq ca-certificates curl gnupg git

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update -y -qq
  apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

  systemctl enable docker
  systemctl start docker
  echo "▶ Docker 설치 완료"
}

if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null 2>&1; then
  install_docker
fi

if ! command -v git &>/dev/null; then
  apt-get install -y -qq git
fi

REPO=/home/ubuntu/discord-image-bot

if [ -d "$REPO" ] && [ ! -d "$REPO/.git" ]; then
  echo "▶ 잔여 디렉토리 정리..."
  rm -rf "$REPO"
fi

if [ ! -d "$REPO/.git" ]; then
  git clone https://github.com/kokospapa8/discord-image-bot.git "$REPO"
fi

cd "$REPO"
chown -R ubuntu:ubuntu "$REPO"
git -c safe.directory="$REPO" fetch origin main
git -c safe.directory="$REPO" reset --hard origin/main

docker compose build --no-cache
docker compose up -d --remove-orphans
docker image prune -f

echo "✅ 배포 완료: $(date)"
