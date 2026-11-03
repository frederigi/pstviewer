#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Fase 1: Diagnóstico de Ambiente Debian / DietPi
# Objetivo: Verificar hardware, armazenamento, pacotes PST, extratores e MySQL
# ==============================================================================
set -euo pipefail

echo "=================================================================="
echo " PST VIEWER - DIAGNÓSTICO TÉCNICO DE AMBIENTE (FASE 1)"
echo " Data/Hora: $(date -Is)"
echo "=================================================================="

echo -e "\n[1] SISTEMA OPERACIONAL E ARQUITETURA"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "  OS: ${PRETTY_NAME:-Desconhecido}"
fi
if [ -f /boot/dietpi/.version ]; then
    echo "  DietPi detectado: $(tr '\n' ' ' < /boot/dietpi/.version)"
fi
echo "  Kernel: $(uname -sr)"
echo "  Arquitetura: $(uname -m) ($(dpkg --print-architecture 2>/dev/null || echo 'N/A'))"
echo "  CPUs/Núcleos: $(nproc)"

echo -e "\n[2] MEMÓRIA RAM E SWAP"
free -h

echo -e "\n[3] ARMAZENAMENTO, SISTEMA DE ARQUIVOS E INODES"
df -hT / /tmp /var /srv 2>/dev/null | uniq
echo -e "\n  Uso de Inodes:"
df -i / /tmp /var /srv 2>/dev/null | uniq

echo -e "\n[4] DISPOSITIVOS DE BLOCO (SSD / HDD / SD / eMMC)"
lsblk -d -o NAME,SIZE,ROTA,DISC-GRAN,MODEL,TYPE 2>/dev/null || true

echo -e "\n[5] VERIFICAÇÃO DE PACOTES E FERRAMENTAS PST (APT / SISTEMA)"
PACKAGES=(
    "python3"
    "python3-venv"
    "python3-pypff"
    "libpff1"
    "pff-tools"
    "pst-utils"
    "default-mysql-server"
    "mariadb-server"
    "nginx"
    "poppler-utils"
    "tesseract-ocr"
    "tesseract-ocr-por"
    "antiword"
    "catdoc"
    "libmagic1"
)

for pkg in "${PACKAGES[@]}"; do
    if dpkg -s "$pkg" >/dev/null 2>&1; then
        ver=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || echo "instalado")
        echo "  [INSTALADO]  $pkg ($ver)"
    else
        cand=$(apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/ {print $2}')
        if [ -n "$cand" ] && [ "$cand" != "(none)" ]; then
            echo "  [DISPONÍVEL] $pkg (Candidato APT: $cand)"
        else
            echo "  [AUSENTE]    $pkg (Não encontrado no repositório atual)"
        fi
    fi
done

echo -e "\n[6] BINÁRIOS DE LEITURA E EXTRAÇÃO NO PATH"
for bin in pffexport pffinfo readpst pdftotext pdfinfo tesseract mysql mysqld mariadb; do
    if command -v "$bin" >/dev/null 2>&1; then
        echo "  [OK] $bin -> $(command -v "$bin")"
    else
        echo "  [--] $bin não instalado no PATH"
    fi
done

echo -e "\n[7] TESTE DE IMPORTAÇÃO DO MÓDULO PYTHON PYPFF"
if python3 -c "import pypff; print('  [OK] pypff versão:', pypff.get_version())" 2>/dev/null; then
    true
else
    echo "  [--] Módulo python3-pypff ainda não instalado no Python do sistema."
fi

echo -e "\n=================================================================="
echo " Diagnóstico concluído."
echo "=================================================================="

