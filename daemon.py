#!/usr/bin/env python3
"""
守护进程 - 监控并自动重启 deepseek.py
监控策略：
1. 进程存活检测
2. 日志文件更新检测（检测是否僵死）
3. 自动重启机制
4. 异常告警
"""

import os
import sys
import time
import subprocess
import signal
import psutil
from datetime import datetime, timedelta
from pathlib import Path
import logging

# 配置守护进程日志
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
daemon_log = log_dir / f"daemon_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DAEMON] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(daemon_log),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

# 配置
CONFIG = {
    'script_path': 'deepseek.py',  # 要监控的脚本
    'python_cmd': sys.executable,  # 使用当前Python解释器
    'check_interval': 60,  # 检查间隔（秒）
    'log_timeout': 300,  # 日志超时时间（秒），5分钟无日志更新视为僵死
    'max_restart_attempts': 3,  # 连续重启最大次数
    'restart_cooldown': 300,  # 重启冷却时间（秒）
    'memory_threshold': 90,  # 内存使用率阈值（%）
}


class ProcessMonitor:
    """进程监控器"""
    
    def __init__(self):
        self.process = None
        self.process_pid = None
        self.last_restart_time = None
        self.restart_count = 0
        self.last_log_mtime = None
        
    def get_latest_log_file(self):
        """获取最新的交易日志文件"""
        try:
            log_files = list(log_dir.glob("trading_*.log"))
            if not log_files:
                return None
            # 返回最新的日志文件
            return max(log_files, key=lambda p: p.stat().st_mtime)
        except Exception as e:
            logger.error(f"获取日志文件失败: {e}")
            return None
    
    def is_process_alive(self):
        """检查进程是否存活"""
        if self.process is None:
            return False
        
        # 检查subprocess对象
        if self.process.poll() is not None:
            logger.warning(f"进程已退出，返回码: {self.process.returncode}")
            return False
        
        # 通过psutil检查进程详情
        try:
            if self.process_pid:
                proc = psutil.Process(self.process_pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return True
                else:
                    logger.warning(f"进程状态异常: {proc.status()}")
                    return False
        except psutil.NoSuchProcess:
            logger.warning(f"进程 PID {self.process_pid} 不存在")
            return False
        except Exception as e:
            logger.error(f"检查进程状态失败: {e}")
            return False
        
        return False
    
    def is_process_frozen(self):
        """检查进程是否僵死（通过日志文件更新时间判断）"""
        log_file = self.get_latest_log_file()
        if not log_file or not log_file.exists():
            logger.warning("未找到交易日志文件，无法判断是否僵死")
            return False
        
        try:
            current_mtime = log_file.stat().st_mtime
            current_time = time.time()
            
            # 计算日志文件距离现在的时间差
            time_since_update = current_time - current_mtime
            
            if time_since_update > CONFIG['log_timeout']:
                logger.warning(
                    f"日志文件 {log_file.name} 已 {int(time_since_update)}秒 未更新，"
                    f"超过阈值 {CONFIG['log_timeout']}秒，判断为僵死"
                )
                return True
            
            # 更新最后日志修改时间
            self.last_log_mtime = current_mtime
            return False
            
        except Exception as e:
            logger.error(f"检查日志文件失败: {e}")
            return False
    
    def check_memory_usage(self):
        """检查进程内存使用率"""
        if not self.process_pid:
            return 0
        
        try:
            proc = psutil.Process(self.process_pid)
            memory_percent = proc.memory_percent()
            
            if memory_percent > CONFIG['memory_threshold']:
                logger.warning(f"进程内存使用率过高: {memory_percent:.2f}%")
                return memory_percent
            
            return memory_percent
        except Exception as e:
            logger.error(f"检查内存使用失败: {e}")
            return 0
    
    def start_process(self):
        """启动交易脚本"""
        try:
            logger.info(f"启动交易脚本: {CONFIG['script_path']}")
            
            # 启动子进程
            self.process = subprocess.Popen(
                [CONFIG['python_cmd'], CONFIG['script_path']],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            self.process_pid = self.process.pid
            logger.info(f"✅ 进程启动成功，PID: {self.process_pid}")
            
            # 重置重启计数（如果距离上次重启超过冷却时间）
            if self.last_restart_time:
                time_since_restart = time.time() - self.last_restart_time
                if time_since_restart > CONFIG['restart_cooldown']:
                    self.restart_count = 0
                    logger.info("重启计数已重置")
            
            self.last_restart_time = time.time()
            return True
            
        except Exception as e:
            logger.error(f"❌ 启动进程失败: {e}")
            return False
    
    def stop_process(self, force=False):
        """停止进程"""
        if not self.process_pid:
            logger.info("没有运行中的进程")
            return True
        
        try:
            proc = psutil.Process(self.process_pid)
            
            if force:
                # 强制终止
                logger.warning(f"强制终止进程 PID: {self.process_pid}")
                proc.kill()
            else:
                # 优雅终止
                logger.info(f"发送 SIGTERM 信号到进程 PID: {self.process_pid}")
                proc.terminate()
                
                # 等待最多10秒
                try:
                    proc.wait(timeout=10)
                    logger.info("进程已优雅退出")
                except psutil.TimeoutExpired:
                    logger.warning("进程未响应 SIGTERM，强制终止")
                    proc.kill()
            
            self.process = None
            self.process_pid = None
            return True
            
        except psutil.NoSuchProcess:
            logger.info(f"进程 PID {self.process_pid} 已不存在")
            self.process = None
            self.process_pid = None
            return True
        except Exception as e:
            logger.error(f"停止进程失败: {e}")
            return False
    
    def restart_process(self):
        """重启进程"""
        logger.info("=" * 60)
        logger.info("🔄 准备重启进程...")
        logger.info("=" * 60)
        
        # 检查重启次数
        self.restart_count += 1
        if self.restart_count > CONFIG['max_restart_attempts']:
            logger.error(
                f"❌ 重启次数超过最大限制 {CONFIG['max_restart_attempts']}，"
                f"请检查脚本是否存在严重问题！"
            )
            logger.error("守护进程将暂停监控，需要人工介入")
            return False
        
        logger.info(f"重启次数: {self.restart_count}/{CONFIG['max_restart_attempts']}")
        
        # 停止旧进程
        if self.is_process_alive():
            self.stop_process(force=True)
            time.sleep(3)  # 等待进程完全退出
        
        # 启动新进程
        success = self.start_process()
        
        if success:
            logger.info(f"✅ 进程重启成功，等待 {CONFIG['check_interval']} 秒后继续监控")
        else:
            logger.error("❌ 进程重启失败")
        
        return success
    
    def monitor(self):
        """主监控循环"""
        logger.info("=" * 60)
        logger.info("🚀 守护进程启动")
        logger.info("=" * 60)
        logger.info(f"监控脚本: {CONFIG['script_path']}")
        logger.info(f"检查间隔: {CONFIG['check_interval']}秒")
        logger.info(f"日志超时: {CONFIG['log_timeout']}秒")
        logger.info(f"最大重启次数: {CONFIG['max_restart_attempts']}")
        logger.info("=" * 60)
        
        # 初次启动
        if not self.start_process():
            logger.error("初次启动失败，退出守护进程")
            return
        
        # 监控循环
        try:
            while True:
                time.sleep(CONFIG['check_interval'])
                
                logger.info(f"🔍 执行健康检查... (PID: {self.process_pid})")
                
                # 1. 检查进程是否存活
                if not self.is_process_alive():
                    logger.error("❌ 进程已退出")
                    if not self.restart_process():
                        break
                    continue
                
                # 2. 检查是否僵死
                if self.is_process_frozen():
                    logger.error("❌ 进程僵死，日志长时间未更新")
                    if not self.restart_process():
                        break
                    continue
                
                # 3. 检查内存使用
                memory_percent = self.check_memory_usage()
                if memory_percent > 0:
                    logger.info(f"📊 内存使用率: {memory_percent:.2f}%")
                
                # 如果内存使用过高，重启进程
                if memory_percent > CONFIG['memory_threshold']:
                    logger.error(f"❌ 内存使用率过高 ({memory_percent:.2f}% > {CONFIG['memory_threshold']}%)")
                    if not self.restart_process():
                        break
                    continue
                
                logger.info("✅ 健康检查通过")
                
        except KeyboardInterrupt:
            logger.info("\n收到中断信号，停止监控...")
            self.stop_process()
            logger.info("守护进程已退出")
        except Exception as e:
            logger.error(f"监控过程发生异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stop_process()


def main():
    """主函数"""
    # 检查脚本是否存在
    if not os.path.exists(CONFIG['script_path']):
        logger.error(f"❌ 找不到脚本文件: {CONFIG['script_path']}")
        sys.exit(1)
    
    # 创建监控器并启动
    monitor = ProcessMonitor()
    monitor.monitor()


if __name__ == "__main__":
    main()
