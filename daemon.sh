#!/bin/bash
# 守护进程管理脚本 - 统一入口
# 用法: ./daemon.sh {start|stop|restart|status}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

PID_FILE="daemon.pid"
LOG_DIR="logs"
DAEMON_SCRIPT="daemon.py"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_success() { echo -e "${GREEN}$1${NC}"; }
print_error() { echo -e "${RED}$1${NC}"; }
print_warning() { echo -e "${YELLOW}$1${NC}"; }
print_info() { echo -e "${BLUE}$1${NC}"; }

# 创建日志目录
mkdir -p "$LOG_DIR"

# 获取守护进程PID
get_daemon_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

# 检查守护进程是否运行
is_daemon_running() {
    local pid=$(get_daemon_pid)
    if [ -z "$pid" ]; then
        return 1
    fi
    
    if ps -p $pid > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 获取交易脚本PID
get_trading_pid() {
    pgrep -f "python.*deepseek.py" | head -n 1
}

# 启动守护进程
start_daemon() {
    print_info "🚀 启动守护进程..."
    
    # 检查是否已经在运行
    if is_daemon_running; then
        local pid=$(get_daemon_pid)
        print_warning "⚠️  守护进程已在运行 (PID: $pid)"
        print_info "如需重启，请执行: $0 restart"
        return 1
    fi
    
    # 清理过期的PID文件
    if [ -f "$PID_FILE" ]; then
        print_info "清理过期的 PID 文件"
        rm -f "$PID_FILE"
    fi
    
    # 检查daemon.py是否存在
    if [ ! -f "$DAEMON_SCRIPT" ]; then
        print_error "❌ 找不到守护进程脚本: $DAEMON_SCRIPT"
        return 1
    fi
    
    # 后台运行守护进程
    nohup python3 "$DAEMON_SCRIPT" > "$LOG_DIR/daemon_output.log" 2>&1 &
    
    # 保存PID
    local daemon_pid=$!
    echo $daemon_pid > "$PID_FILE"
    
    # 等待1秒确认启动成功
    sleep 1
    
    if is_daemon_running; then
        print_success "✅ 守护进程已启动 (PID: $daemon_pid)"
        echo ""
        print_info "📋 日志文件:"
        echo "   - 守护进程日志: $LOG_DIR/daemon_$(date +%Y%m%d).log"
        echo "   - 输出日志: $LOG_DIR/daemon_output.log"
        echo ""
        print_info "💡 管理命令:"
        echo "   查看状态: $0 status"
        echo "   查看日志: tail -f $LOG_DIR/daemon_$(date +%Y%m%d).log"
        echo "   停止守护: $0 stop"
        echo "   重启守护: $0 restart"
        return 0
    else
        print_error "❌ 守护进程启动失败"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 停止守护进程
stop_daemon() {
    print_info "🛑 停止守护进程..."
    
    if ! is_daemon_running; then
        print_warning "⚠️  守护进程未运行"
        rm -f "$PID_FILE"
        return 0
    fi
    
    local pid=$(get_daemon_pid)
    print_info "发送 SIGTERM 信号到进程 (PID: $pid)..."
    
    # 发送 SIGTERM 信号
    kill $pid 2>/dev/null
    
    # 等待进程退出（最多10秒）
    local count=0
    while [ $count -lt 10 ]; do
        if ! ps -p $pid > /dev/null 2>&1; then
            print_success "✅ 守护进程已停止"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    
    # 如果还没退出，强制终止
    print_warning "⚠️  进程未响应，强制终止..."
    kill -9 $pid 2>/dev/null
    sleep 1
    
    if ! ps -p $pid > /dev/null 2>&1; then
        print_success "✅ 守护进程已强制停止"
        rm -f "$PID_FILE"
        return 0
    else
        print_error "❌ 无法停止守护进程"
        return 1
    fi
}

# 重启守护进程
restart_daemon() {
    print_info "🔄 重启守护进程..."
    echo ""
    
    stop_daemon
    sleep 2
    start_daemon
}

# 查看状态
show_status() {
    echo "================================================================"
    print_info "📊 守护进程状态"
    echo "================================================================"
    
    # 检查守护进程
    if is_daemon_running; then
        local daemon_pid=$(get_daemon_pid)
        print_success "✅ 守护进程: 运行中"
        echo "   PID: $daemon_pid"
        
        # 显示进程详情
        if command -v ps &> /dev/null; then
            echo "   详情: $(ps -p $daemon_pid -o pid,ppid,%cpu,%mem,etime,command | tail -n 1)"
        fi
    else
        print_error "❌ 守护进程: 未运行"
        rm -f "$PID_FILE"
        echo ""
        print_info "💡 启动守护进程: $0 start"
        return 1
    fi
    
    echo ""
    
    # 检查被监控的进程
    local trading_pid=$(get_trading_pid)
    
    if [ -n "$trading_pid" ]; then
        print_success "✅ 交易脚本: 运行中"
        echo "   PID: $trading_pid"
        
        if command -v ps &> /dev/null; then
            echo "   详情: $(ps -p $trading_pid -o pid,ppid,%cpu,%mem,etime,command | tail -n 1)"
        fi
    else
        print_warning "⚠️  交易脚本: 未运行"
    fi
    
    echo ""
    echo "================================================================"
    print_info "📋 最近日志 (守护进程)"
    echo "================================================================"
    
    local latest_daemon_log="$LOG_DIR/daemon_$(date +%Y%m%d).log"
    if [ -f "$latest_daemon_log" ]; then
        echo "日志文件: $latest_daemon_log"
        echo ""
        tail -n 10 "$latest_daemon_log"
    else
        print_warning "未找到今日守护进程日志"
    fi
    
    echo ""
    echo "================================================================"
    print_info "📋 最近日志 (交易脚本)"
    echo "================================================================"
    
    local latest_trading_log="$LOG_DIR/trading_$(date +%Y%m%d).log"
    if [ -f "$latest_trading_log" ]; then
        echo "日志文件: $latest_trading_log"
        echo ""
        tail -n 10 "$latest_trading_log"
    else
        print_warning "未找到今日交易日志"
    fi
    
    echo ""
    echo "================================================================"
    print_info "💡 管理命令"
    echo "================================================================"
    echo "   启动: $0 start"
    echo "   停止: $0 stop"
    echo "   重启: $0 restart"
    echo "   状态: $0 status"
    echo ""
    echo "   实时日志 (守护): tail -f $latest_daemon_log"
    echo "   实时日志 (交易): tail -f $latest_trading_log"
    echo "================================================================"
}

# 显示帮助信息
show_usage() {
    echo "用法: $0 {start|stop|restart|status}"
    echo ""
    echo "命令说明:"
    echo "  start   - 启动守护进程"
    echo "  stop    - 停止守护进程"
    echo "  restart - 重启守护进程"
    echo "  status  - 查看运行状态"
    echo ""
    echo "示例:"
    echo "  $0 start    # 启动守护进程"
    echo "  $0 status   # 查看状态"
    echo "  $0 restart  # 重启守护进程"
}

# 主函数
main() {
    case "$1" in
        start)
            start_daemon
            ;;
        stop)
            stop_daemon
            ;;
        restart)
            restart_daemon
            ;;
        status)
            show_status
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
