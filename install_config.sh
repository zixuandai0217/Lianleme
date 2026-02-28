#!/bin/bash

# ========================================
# VibeConfig 安装脚本
# 支持: macOS, Linux, Windows (Git Bash/MSYS2/Cygwin)
# ========================================

set -e  # 任何命令失败立即退出

# 设置仓库地址
REPO_URL="https://github.com/zixuandai0217/VibeConfig.git"
TEMP_DIR=$(mktemp -d)

# ========================================
# 颜色和样式定义
# ========================================
# 检测是否支持颜色
if [ -t 1 ] && command -v tput >/dev/null 2>&1; then
    COLORS_SUPPORTED=true
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    CYAN=$(tput setaf 6)
    WHITE=$(tput setaf 7)
    BOLD=$(tput bold)
    DIM=$(tput dim)
    RESET=$(tput sgr0)
else
    COLORS_SUPPORTED=false
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    MAGENTA=""
    CYAN=""
    WHITE=""
    BOLD=""
    DIM=""
    RESET=""
fi

# 图标定义（兼容不支持 Unicode 的终端）
if printf '\u2713' 2>/dev/null | grep -q .; then
    ICON_OK="✓"
    ICON_FAIL="✗"
    ICON_WARN="⚠"
    ICON_INFO="ℹ"
    ICON_ARROW="→"
    ICON_ROCKET="🚀"
    ICON_PACKAGE="📦"
    ICON_GEAR="⚙"
    ICON_CHECK="✔"
else
    ICON_OK="[OK]"
    ICON_FAIL="[X]"
    ICON_WARN="[!]"
    ICON_INFO "[i]"
    ICON_ARROW="->"
    ICON_ROCKET="*"
    ICON_PACKAGE="[backup]"
    ICON_GEAR="*"
    ICON_CHECK="[done]"
fi

# ========================================
# 输出函数
# ========================================
print_header() {
    echo ""
    echo "${CYAN}${BOLD}╔════════════════════════════════════════╗${RESET}"
    echo "${CYAN}${BOLD}║${RESET}                                        ${CYAN}${BOLD}║${RESET}"
    echo "${CYAN}${BOLD}║${RESET}      ${MAGENTA}${BOLD}VibeConfig 安装脚本${RESET}              ${CYAN}${BOLD}║${RESET}"
    echo "${CYAN}${BOLD}║${RESET}                                        ${CYAN}${BOLD}║${RESET}"
    echo "${CYAN}${BOLD}╚════════════════════════════════════════╝${RESET}"
    echo ""
}

print_step() {
    local step_num=$1
    local total=$2
    local message=$3
    echo ""
    echo "${BLUE}${BOLD}[$step_num/$total]${RESET} ${WHITE}${BOLD}$message${RESET}"
    echo "${DIM}────────────────────────────────────────${RESET}"
}

print_success() {
    echo "  ${GREEN}${ICON_OK}${RESET} $1"
}

print_error() {
    echo "  ${RED}${ICON_FAIL}${RESET} $1"
}

print_warning() {
    echo "  ${YELLOW}${ICON_WARN}${RESET} $1"
}

print_info() {
    echo "  ${CYAN}${ICON_INFO}${RESET} $1"
}

print_subtask() {
    echo "    ${DIM}${ICON_ARROW}${RESET} $1"
}

# 进度条显示函数
print_progress() {
    local current=$1
    local total=$2
    local step_name=$3
    local detail=$4

    local percent=$((current * 100 / total))
    local bar_width=40
    local filled=$((percent * bar_width / 100))
    local empty=$((bar_width - filled))

    # 构建进度条
    local progress_bar="["
    local i=1
    while [ $i -le $filled ]; do
        progress_bar="${progress_bar}█"
        i=$((i + 1))
    done
    while [ $i -le $bar_width ]; do
        progress_bar="${progress_bar}░"
        i=$((i + 1))
    done
    progress_bar="${progress_bar}]"

    # 动态输出进度行
    printf "\r${CYAN}进度 ${progress_bar} ${percent}%% ${WHITE}${step_name}${RESET}"
    if [ -n "$detail" ]; then
        printf " ${DIM}- ${detail}${RESET}"
    fi
    printf "\n"
}

# 更新进度的单行显示
update_progress_detail() {
    local detail=$1
    printf "${DIM}  └─ %s${RESET}\n" "$detail"
}

print_banner() {
    echo ""
    echo "${GREEN}${BOLD}╔════════════════════════════════════════╗${RESET}"
    echo "${GREEN}${BOLD}║${RESET}                                        ${GREEN}${BOLD}║${RESET}"
    echo "${GREEN}${BOLD}║${RESET}       ${WHITE}${BOLD}🎉 所有步骤完成！${RESET}                  ${GREEN}${BOLD}║${RESET}"
    echo "${GREEN}${BOLD}║${RESET}                                        ${GREEN}${BOLD}║${RESET}"
    echo "${GREEN}${BOLD}╚════════════════════════════════════════╝${RESET}"
    echo ""
}

# 跨平台兼容性: 获取当前时间戳
get_timestamp() {
    date +%Y%m%d%H%M%S 2>/dev/null || date +"%Y%m%d%H%M%S"
}

# 跨平台兼容性: 备份文件/目录
backup_if_exists() {
    local item="$1"
    if [ -e "$item" ]; then
        local backup_name="${item}.bak.$(get_timestamp)"
        print_subtask "${ICON_PACKAGE} 备份已存在的 $item -> $backup_name"
        mv "$item" "$backup_name"
    fi
}

# 安全退出: 清理临时目录
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

# 检测操作系统类型
detect_os() {
    case "$OSTYPE" in
        darwin*)  echo "macos" ;;
        linux*)   echo "linux" ;;
        msys*|cygwin*) echo "windows" ;;
        *)        echo "unknown" ;;
    esac
}

OS_TYPE=$(detect_os)
print_header
print_info "检测到系统: ${BOLD}$OS_TYPE${RESET}"

# ========================================
# Step 1: 克隆远程仓库
# ========================================
print_step 1 8 "克隆远程仓库"
print_progress 1 8 "克隆远程仓库" "正在从 $REPO_URL 克隆..."

if ! git clone --depth 1 "$REPO_URL" "$TEMP_DIR" 2>/dev/null; then
    print_error "克隆失败，请检查网络或仓库地址。"
    exit 1
fi
update_progress_detail "仓库克隆完成"
print_success "仓库克隆完成"

# ========================================
# Step 2: 备份并复制配置文件
# ========================================
print_step 2 8 "复制配置文件"
print_progress 2 8 "复制配置文件" "正在备份已存在的文件..."

# 备份已存在的文件
for item in ".trae" ".claude" "AGENTS.md" "CLAUDE.md"; do
    backup_if_exists "$item"
done

update_progress_detail "正在复制配置文件..."

# 复制文件（带错误检查）
copy_item() {
    local src="$1"
    local name="$2"
    if [ -e "$src" ]; then
        if ! cp -r "$src" . 2>/dev/null; then
            print_error "复制 $name 失败"
            exit 1
        fi
        print_success "$name 已复制"
    else
        print_warning "$name 在仓库中不存在，跳过"
    fi
}

copy_item "$TEMP_DIR/.trae" ".trae"
copy_item "$TEMP_DIR/.claude" ".claude"
copy_item "$TEMP_DIR/AGENTS.md" "AGENTS.md"
copy_item "$TEMP_DIR/CLAUDE.md" "CLAUDE.md"

update_progress_detail "配置文件复制完成"
print_info "配置文件复制完成"

# ========================================
# Step 3: 安装 Hooks 音效配置
# ========================================
print_step 3 8 "安装 Hooks 音效配置"
print_progress 3 8 "安装 Hooks 音效配置" "正在检测音频播放器..."

# 检测可用的音频播放工具
AUDIO_PLAYER=""
if command -v afplay >/dev/null 2>&1; then
    AUDIO_PLAYER="afplay"
    print_success "检测到 afplay (macOS 原生音频播放器)"
elif command -v ffplay >/dev/null 2>&1; then
    AUDIO_PLAYER="ffplay"
    print_success "检测到 ffplay (FFmpeg)"
else
    print_warning "未检测到音频播放器"
    update_progress_detail "提示：macOS 自带 afplay 命令，无需安装"

    # 询问用户是否要安装音频播放器
    case "$OS_TYPE" in
        windows)
            print_info "Windows 用户需要安装 FFmpeg 才能播放音效"
            print_subtask "下载地址：https://ffmpeg.org/download.html"
            print_subtask "安装后请将 FFmpeg 添加到 PATH 环境变量"
            ;;
        macos)
            print_info "macOS 用户可使用系统自带 afplay 命令 (无需安装)"
            print_subtask "或选择安装 Homebrew + ffmpeg 获得更多功能"
            ;;
        linux)
            print_info "Linux 用户需要安装 ffmpeg"
            ;;
    esac

    # 兼容 zsh 和 bash 的 read 命令
    if [ -n "$ZSH_VERSION" ]; then
        read "REPLY?    是否继续安装 Hooks 配置? (y/n) "
    else
        read -p "    是否继续安装 Hooks 配置？(y/n) " -r
    fi
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "已跳过 Hooks 音效配置安装"
    fi
fi

# 检查项目中是否有 hooks 配置
if [ -d "$TEMP_DIR/.claude/hooks" ]; then
    print_progress 3 8 "安装 Hooks 音效配置" "正在复制 hooks 配置..."
    update_progress_detail "正在复制 hooks 音效配置..."

    # 备份已存在的 hooks
    if [ -d ".claude/hooks" ]; then
        backup_if_exists ".claude/hooks"
    fi

    # 创建 .claude/hooks 目录
    mkdir -p ".claude/hooks"

    # 复制 hooks 文件
    if cp -r "$TEMP_DIR/.claude/hooks/"* ".claude/hooks/" 2>/dev/null; then
        print_success "Hooks 音效配置已复制"
        print_subtask "音效文件："
        for file in ".claude/hooks/"*.ogg ".claude/hooks/"*.mp3; do
            if [ -f "$file" ]; then
                echo "      - $file"
            fi
        done

        # 检测系统类型并更新 config.json 中的路径
        HOOKS_CONFIG=".claude/hooks/config.json"
        if [ -f "$HOOKS_CONFIG" ]; then
            update_progress_detail "正在配置路径格式..."
            print_subtask "正在配置路径格式..."
            if command -v python3 >/dev/null 2>&1; then
                python3 << 'PYTHON_SCRIPT'
import json
import os
import sys

config_path = '.claude/hooks/config.json'

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 获取用户主目录
    user_home = os.path.expanduser('~')

    # 检测操作系统类型
    is_windows = os.name == 'nt' or sys.platform == 'win32'
    is_macos = sys.platform == 'darwin'

    # 检测可用的音频播放器
    def get_audio_player():
        import subprocess
        try:
            subprocess.run(['afplay', '--help'], capture_output=True, timeout=1)
            return 'afplay'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        try:
            subprocess.run(['ffplay', '-version'], capture_output=True, timeout=1)
            return 'ffplay'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    audio_player = get_audio_player()

    def update_path(cmd):
        # 提取文件名（兼容反斜杠和正斜杠）
        filename = cmd.replace('\\', '/').split('/')[-1]

        if audio_player == 'afplay':
            # macOS afplay 命令
            return f'afplay {user_home}/.claude/hooks/{filename}'
        elif audio_player == 'ffplay':
            # ffplay 命令
            if is_windows:
                return f'ffplay -nodisp -autoexit {user_home}\\.claude\\hooks\\{filename}'
            else:
                return f'ffplay -nodisp -autoexit {user_home}/.claude/hooks/{filename}'
        else:
            # 没有可用的播放器，保持原样或返回空
            return cmd

    # 更新所有 hooks 命令
    for event in data.get('hooks', {}):
        for hook in data['hooks'][event]:
            if hook.get('type') == 'command':
                hook['command'] = update_path(hook['command'])

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT
                if [ $? -eq 0 ]; then
                    if [ "$AUDIO_PLAYER" = "afplay" ]; then
                        print_success "已自动配置 afplay 音效播放"
                    elif [ "$AUDIO_PLAYER" = "ffplay" ]; then
                        print_success "已自动配置 ffplay 音效播放"
                    else
                        print_success "已自动更新 config.json 路径配置"
                    fi
                else
                    print_warning "自动更新 config.json 失败，请手动修改"
                fi
            else
                print_warning "未检测到 python3，无法自动更新 config.json"
            fi
        fi
    else
        print_warning "复制 hooks 配置失败"
    fi
else
    print_info "项目中没有找到 hooks 配置，跳过音效安装"
fi

# ========================================
# Step 4: 初始化 uv 项目（幂等处理）
# ========================================
print_step 4 8 "检查 uv 项目"
print_progress 4 8 "检查 uv 项目" "正在检查 pyproject.toml..."

if [ -f "pyproject.toml" ]; then
    print_info "pyproject.toml 已存在，跳过 uv init"
elif command -v uv >/dev/null 2>&1; then
    print_subtask "正在初始化 uv 项目..."
    uv init 2>/dev/null
    update_progress_detail "uv 项目初始化完成"
    print_success "uv 项目初始化完成"
else
    print_warning "未检测到 uv 命令，跳过 uv init"
    print_subtask "提示: 可通过 https://docs.astral.sh/uv/ 安装 uv"
fi

# ========================================
# Step 5: 安装 Claude Code
# ========================================
print_step 5 8 "检查 Claude Code"
print_progress 5 8 "检查 Claude Code" "正在检查 Claude Code 安装状态..."

if command -v claude >/dev/null 2>&1; then
    update_progress_detail "Claude Code 已安装"
    print_success "Claude Code 已安装"
else
    print_warning "Claude Code 未安装"
    case "$OS_TYPE" in
        windows)
            print_info "检测到 Windows 环境 (Git Bash)"
            echo ""
            print_subtask "请使用 PowerShell (管理员) 运行:"
            echo "      ${CYAN}irm https://claude.ai/install.ps1 | iex${RESET}"
            echo ""
            print_subtask "或在 CMD 中运行:"
            echo "      ${CYAN}curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd${RESET}"
            ;;
        macos|linux)
            INSTALL_SCRIPT="/tmp/claude_install_$$.sh"
            print_subtask "正在下载安装脚本..."
            update_progress_detail "正在下载安装脚本..."
            if curl -fsSL https://claude.ai/install.sh -o "$INSTALL_SCRIPT" 2>/dev/null; then
                print_success "安装脚本已下载到: $INSTALL_SCRIPT"
                echo ""
                if [ -n "$ZSH_VERSION" ]; then
                    read "REPLY?    是否执行安装脚本? (y/n) "
                else
                    read -p "    是否执行安装脚本? (y/n) " -r
                fi
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    bash "$INSTALL_SCRIPT"
                else
                    print_info "已跳过安装，可稍后手动执行: bash $INSTALL_SCRIPT"
                fi
                rm -f "$INSTALL_SCRIPT"
            else
                print_error "下载安装脚本失败，请手动安装 Claude Code"
            fi
            ;;
        *)
            print_warning "未知系统类型，请手动安装 Claude Code"
            ;;
    esac
fi

# ========================================
# Step 6: 安装 cc-switch (仅 macOS + Homebrew)
# ========================================
print_step 6 8 "检查 cc-switch"
print_progress 6 8 "检查 cc-switch" "正在检查 Homebrew 和 cc-switch..."

if [ "$OS_TYPE" = "macos" ]; then
    if command -v brew >/dev/null 2>&1; then
        print_info "cc-switch 是 Claude Code 版本管理工具"
        update_progress_detail "可通过 Homebrew 安装：brew install --cask cc-switch"
        print_subtask "可通过 Homebrew 安装：brew install --cask cc-switch"

        # 兼容 zsh 和 bash 的 read 命令
        if [ -n "$ZSH_VERSION" ]; then
            read "REPLY?    是否安装 cc-switch? (y/n) "
        else
            read -p "    是否安装 cc-switch? (y/n) " -r
        fi
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_subtask "正在安装 cc-switch..."
            update_progress_detail "正在执行：brew install --cask cc-switch..."
            brew tap farion1231/ccswitch 2>/dev/null
        if brew install --cask cc-switch 2>/dev/null || brew upgrade --cask cc-switch 2>/dev/null; then
            print_success "cc-switch 安装成功"
            else
                print_warning "cc-switch 安装失败，请手动安装"
            fi
        else
            print_info "已跳过 cc-switch 安装"
        fi
    else
        print_warning "未检测到 Homebrew，跳过 cc-switch 安装"
        print_subtask "提示: 可通过 https://brew.sh 安装 Homebrew"
    fi
else
    print_info "cc-switch 仅支持 macOS + Homebrew，跳过"
fi

# ========================================
# Step 7: 配置 .claude.json
# ========================================
print_step 7 8 "配置 .claude.json"
print_progress 7 8 "配置 .claude.json" "正在检查 ~/.claude.json..."

CLAUDE_CONFIG="$HOME/.claude.json"

if [ ! -f "$CLAUDE_CONFIG" ]; then
    echo '{ "hasCompletedOnboarding": true }' > "$CLAUDE_CONFIG"
    print_success "已创建 .claude.json 并设置 hasCompletedOnboarding: true"
else
    if grep -q "hasCompletedOnboarding" "$CLAUDE_CONFIG" 2>/dev/null; then
        print_success ".claude.json 已包含 hasCompletedOnboarding 配置"
    else
        # 尝试使用 Python 修改 JSON（跨平台兼容）
        if command -v python3 >/dev/null 2>&1; then
            python3 -c "
import json
import sys
config_path = '$CLAUDE_CONFIG'
try:
    with open(config_path, 'r') as f:
        data = json.load(f)
    data['hasCompletedOnboarding'] = True
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null && result="success" || result="failed"

            if [ "$result" = "success" ]; then
                print_success "已更新 .claude.json (via Python)"
            else
                # Fallback: 使用 sed（跨平台兼容方式）
                tmp_file=$(mktemp)
                if printf '{\n  \"hasCompletedOnboarding\": true,\n' > "$tmp_file" && \
                   tail -c +3 "$CLAUDE_CONFIG" >> "$tmp_file" && \
                   mv "$tmp_file" "$CLAUDE_CONFIG"; then
                    print_success "已更新 .claude.json (via fallback)"
                else
                    rm -f "$tmp_file"
                    print_warning "自动更新失败，请手动添加 hasCompletedOnboarding: true 到 $CLAUDE_CONFIG"
                fi
            fi
        else
            # 无 Python，使用 sed
            tmp_file=$(mktemp)
            if printf '{\n  \"hasCompletedOnboarding\": true,\n' > "$tmp_file" && \
               tail -c +3 "$CLAUDE_CONFIG" >> "$tmp_file" && \
               mv "$tmp_file" "$CLAUDE_CONFIG"; then
                print_success "已更新 .claude.json"
            else
                rm -f "$tmp_file"
                print_warning "自动更新失败，请手动添加 hasCompletedOnboarding: true 到 $CLAUDE_CONFIG"
            fi
        fi
    fi
fi

# ========================================
# Step 8: 初始化 Git 仓库并提交
# ========================================
print_step 8 8 "配置 Git 仓库"
print_progress 8 8 "配置 Git 仓库" "正在检查 Git 仓库状态..."

if [ ! -d ".git" ]; then
    print_subtask "正在初始化 Git 仓库..."
    update_progress_detail "正在执行：git init..."
    git init 2>/dev/null
    update_progress_detail "Git 仓库初始化完成"
    print_success "Git 仓库初始化完成"
else
    print_info "Git 仓库已存在，跳过 git init"
fi

print_subtask "正在添加配置文件并提交..."
update_progress_detail "正在执行：git add && git commit..."
git add ".trae" ".claude" "AGENTS.md" "CLAUDE.md" 2>/dev/null || true
if git commit -m "chore: 初始化 VibeConfig 配置" 2>/dev/null; then
    print_success "配置文件已提交到 Git"
else
    print_info "没有更改需要提交"
fi

# 添加 hooks 音效配置到 Git 版本控制
if [ -d ".claude/hooks" ] && [ "$(ls -A .claude/hooks 2>/dev/null)" ]; then
    print_subtask "正在添加 hooks 音效配置到 Git..."
    update_progress_detail "正在执行：git add && git commit (hooks)..."
    git add ".claude/hooks/" 2>/dev/null || true
    if git commit -m "feat: 添加 Hooks 音效配置" 2>/dev/null; then
        print_success "Hooks 音效配置已提交到 Git"
    else
        print_info "没有新的更改需要提交"
    fi
fi

# ========================================
# 完成
# ========================================
printf "\r${GREEN}${BOLD}进度 [████████████████████████████████████████] 100%% 安装完成！${RESET}\n\n"

print_banner

# 询问是否启动 Claude（跨平台兼容）
if [ "$OS_TYPE" != "windows" ]; then
    if command -v claude >/dev/null 2>&1; then
        # 兼容 zsh 和 bash 的 read 命令
        if [ -n "$ZSH_VERSION" ]; then
            read "REPLY?    ${CYAN}是否立即启动 Claude Code? (y/n)${RESET} "
        else
            read -p "    ${CYAN}是否立即启动 Claude Code? (y/n)${RESET} " -r
        fi
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_subtask "启动 Claude Code..."
            exec claude
        fi
    else
        print_info "Claude Code 未安装，请先完成安装后手动启动"
    fi
else
    print_info "Windows 环境请手动启动 Claude Code"
fi

echo ""
print_subtask "配置文件位置: ${BOLD}$(pwd)${RESET}"
echo ""
echo "${MAGENTA}感谢使用 VibeConfig!${RESET}"