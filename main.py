import readline  # 提供标准行编辑（退格、方向键等）
import asyncio
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown

from src.workflow import system
from src.tools.rag_manager import rag_manager


console = Console()


class FinancialCLI:
    def __init__(self):
        self.system = system
        self.running = True
        self.iteration_log = []
        self.conversation_history = []
    
    def print_welcome(self):
        welcome_text = """
# 金融投研问答与报告生成系统

基于 LangGraph 的多智能体金融分析系统 (ReAct 模式)

**功能特性:**
- 📊 股票行情查询与分析
- 📈 技术指标计算与趋势判断  
- 📝 投研报告自动生成
- 📄 文档解析与知识库问答
- 🔍 财务数据采集与分析

**使用方式:** 直接输入问题即可
- "贵州茅台股价多少？"
- "分析600519的技术指标"
- "生成茅台投研报告"
- 输入 quit 退出
        """
        console.print(Panel(Markdown(welcome_text), title="欢迎使用", border_style="blue"))
    
    def _extract_file_paths(self, text: str) -> list:
        patterns = [
            r'[A-Za-z]:\\[^\s<>"|*?\n]+',
            r'/[^\s<>"|*?\n]+',
        ]
        
        paths = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            paths.extend(matches)
        
        valid_paths = []
        for path in paths:
            clean_path = path.rstrip('.,;:!?')
            if os.path.exists(clean_path):
                valid_paths.append(clean_path)
        
        return valid_paths
    
    def _print_iteration_detail(self, agent_name: str, thought: str, action: str, observation: str, iteration: int):
        console.print(f"\n[bold white on blue] 迭代 {iteration} [/bold white on blue] [cyan]{agent_name}[/cyan]")
        
        if thought:
            console.print(f"  [yellow]💭 Thought:[/yellow] {thought}")
        
        if action:
            console.print(f"  [cyan]🎯 Action:[/cyan] {action}")
        
        if observation:
            obs_display = observation[:300] + "..." if len(observation) > 300 else observation
            console.print(f"  [green]👁 Observation:[/green] {obs_display}")
        
        self.iteration_log.append({
            "agent": agent_name,
            "thought": thought,
            "action": action,
            "observation": observation,
            "iteration": iteration
        })
    
    async def process_query(self, query: str):
        file_paths = self._extract_file_paths(query)
        
        console.print()
        
        self.iteration_log = []
        final_state = None
        current_agent = None
        iteration_count = 0
        current_state = None
        
        async for node_name, node_output in self.system.run_stream(
            query, 
            file_paths=file_paths if file_paths else None,
            conversation_history=self.conversation_history
        ):
            if node_name == "final":
                final_state = node_output
                break
            
            current_state = node_output
            
            if node_name == "wait_for_user":
                question = node_output.get("need_user_input", "请提供更多信息")
                console.print(f"\n[yellow]❓ {question}[/yellow]")
                user_response = Prompt.ask("[bold cyan]请输入[/bold cyan]")
                
                current_state["user_response"] = user_response
                current_state["query"] = f"{query} {user_response}"
                current_state["need_user_input"] = None
                
                async for continue_node_name, continue_node_output in self.system.run_stream(
                    current_state["query"],
                    file_paths=file_paths if file_paths else None,
                    conversation_history=self.conversation_history
                ):
                    if continue_node_name == "final":
                        final_state = continue_node_output
                        break
                    current_state = continue_node_output
                    
                    if continue_node_name == "dispatcher":
                        agent_name = continue_node_output.get("current_agent", "DispatcherAgent")
                        thought = continue_node_output.get("thought", "")
                        action = continue_node_output.get("action", "")
                        selected = continue_node_output.get("selected_agent", "")
                        
                        if thought or action:
                            iteration_count += 1
                            self._print_iteration_detail(agent_name, thought, action, "", iteration_count)
                        
                        console.print(f"[bold green]🎯 调度到: {selected}[/bold green]")
                        current_agent = selected
                    
                    elif continue_node_name in ["data_agent", "analysis_agent", "qa_agent", "report_agent", "file_processing_agent"]:
                        agent_name = continue_node_output.get("current_agent", continue_node_name)
                        iteration_logs = continue_node_output.get("iteration_logs", [])
                        
                        if iteration_logs:
                            for log in iteration_logs:
                                iteration_count += 1
                                self._print_iteration_detail(
                                    agent_name, 
                                    log.get("thought", ""), 
                                    log.get("action", ""), 
                                    log.get("observation", ""), 
                                    iteration_count
                                )
                        else:
                            thought = continue_node_output.get("thought", "")
                            action = continue_node_output.get("action", "")
                            observation = continue_node_output.get("observation", "")
                            
                            if thought or action:
                                iteration_count += 1
                                self._print_iteration_detail(agent_name, thought, action, observation, iteration_count)
                        
                        if continue_node_output.get("is_finished"):
                            console.print(f"  [dim]✅ {agent_name} 任务完成[/dim]")
                
                break
            
            if node_name == "dispatcher":
                agent_name = node_output.get("current_agent", "DispatcherAgent")
                thought = node_output.get("thought", "")
                action = node_output.get("action", "")
                selected = node_output.get("selected_agent", "")
                
                if thought or action:
                    iteration_count += 1
                    self._print_iteration_detail(agent_name, thought, action, "", iteration_count)
                
                console.print(f"[bold green]🎯 调度到: {selected}[/bold green]")
                current_agent = selected
            
            elif node_name in ["data_agent", "analysis_agent", "qa_agent", "report_agent", "file_processing_agent"]:
                agent_name = node_output.get("current_agent", node_name)
                iteration_logs = node_output.get("iteration_logs", [])
                
                if iteration_logs:
                    for log in iteration_logs:
                        iteration_count += 1
                        self._print_iteration_detail(
                            agent_name, 
                            log.get("thought", ""), 
                            log.get("action", ""), 
                            log.get("observation", ""), 
                            iteration_count
                        )
                else:
                    thought = node_output.get("thought", "")
                    action = node_output.get("action", "")
                    observation = node_output.get("observation", "")
                    
                    if thought or action:
                        iteration_count += 1
                        self._print_iteration_detail(agent_name, thought, action, observation, iteration_count)
                
                if node_output.get("is_finished"):
                    console.print(f"  [dim]✅ {agent_name} 任务完成[/dim]")
        
        if final_state:
            if final_state.get("error"):
                console.print(f"\n[red]❌ 错误: {final_state['error']}[/red]")
                return
            
            answer = final_state.get("answer") or final_state.get("report", "")

            # ─── 写入混合记忆 (L1 会话上下文 + L2 查询历史) ───
            if hasattr(self.system, 'hybrid_memory') and self.system.hybrid_memory:
                try:
                    self.system.hybrid_memory.record_turn("user", query)
                    self.system.hybrid_memory.record_turn("assistant", answer[:200])
                except Exception:
                    pass

            self.conversation_history.append({
                "question": query,
                "answer": answer
            })
            
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            if final_state.get("report"):
                console.print("\n")
                console.print(Panel(
                    Markdown(final_state["report"]),
                    title="📊 投研报告",
                    border_style="green"
                ))
                
                report_path = final_state.get("metadata", {}).get("report_path", "")
                if report_path:
                    console.print(f"[dim]📄 报告已保存至: {report_path}[/dim]")
                    
            elif final_state.get("answer"):
                console.print("\n")
                answer_text = final_state["answer"]
                
                # 夣理图片显示
                charts = final_state.get("charts", [])
                if charts:
                    console.print(Panel(
                        Markdown(answer_text),
                        title="💡 回答",
                        border_style="blue"
                    ))
                    
                    # 显示图片链接
                    console.print("\n[bold cyan]📊 生成的图表:[/bold cyan]")
                    for chart in charts:
                        if isinstance(chart, dict) and "path" in chart:
                            chart_path = chart["path"]
                            chart_type = chart.get("type", "unknown")
                            console.print(f"  • [{chart_type}图] {chart_path}")
                else:
                    console.print(Panel(
                        Markdown(answer_text),
                        title="💡 回答",
                        border_style="blue"
                    ))
            else:
                console.print("\n[yellow]未能生成有效回答[/yellow]")
            
            # 显示处理数据统计
            collected_data = final_state.get("collected_data", [])
            if collected_data:
                console.print("\n[bold cyan]📦 收集的数据:[/bold cyan]")
                if isinstance(collected_data, list):
                    # 新的列表格式
                    sources = set()
                    for item in collected_data:
                        if isinstance(item, dict):
                            src = item.get("source") or item.get("data_source") or "未知"
                            sources.add(src)
                    for src in sorted(sources):
                        count = sum(1 for item in collected_data
                                   if isinstance(item, dict) and
                                   (item.get("source") == src or item.get("data_source") == src))
                        console.print(f"  • {src}: {count} 条")
                elif isinstance(collected_data, dict):
                    for key, value in collected_data.items():
                        if isinstance(value, list):
                            console.print(f"  • {key}: {len(value)} 条")
                        elif isinstance(value, dict):
                            console.print(f"  • {key}: {len(value)} 个字段")
                        else:
                            console.print(f"  • {key}: 已获取")
            
            # 显示分析结果
            analysis_results = final_state.get("analysis_results", [])
            if analysis_results:
                console.print(f"\n[bold cyan]📈 分析结果: {len(analysis_results)} 项[/bold cyan]")
            
            token_usage = final_state.get("metadata", {}).get("token_usage", {})
            if token_usage and token_usage.get("total", 0) > 0:
                console.print(
                    f"[dim]📊 Token 消耗: "
                    f"输入 {token_usage.get('prompt', 0)} + "
                    f"输出 {token_usage.get('completion', 0)} = "
                    f"总计 {token_usage.get('total', 0)}[/dim]"
                )
    
    async def run(self):
        self.print_welcome()
        
        while self.running:
            try:
                user_input = input("\n请输入问题: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ["quit", "exit", "q"]:
                    console.print("[yellow]感谢使用，再见！[/yellow]")
                    self.running = False
                    continue
                
                await self.process_query(user_input)
                
            except KeyboardInterrupt:
                console.print("\n[yellow]输入 quit 退出程序[/yellow]")
            except asyncio.CancelledError:
                console.print("\n[yellow]请求被取消，请重试[/yellow]")
            except Exception as e:
                console.print(f"[red]错误: {str(e)}[/red]")


async def main():
    cli = FinancialCLI()
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
