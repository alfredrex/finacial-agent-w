import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.workflow import MultiAgentSystem

async def test_moutai_report():
    workflow = MultiAgentSystem()
    
    query = "茅台深度报告"
    print(f"\n{'='*60}")
    print(f"测试查询: {query}")
    print(f"{'='*60}\n")
    
    initial_state = {
        "query": query,
        "messages": [],
        "collected_data": {},
        "charts": [],
        "report": None,
        "answer": None,
    }
    
    try:
        async for node_name, node_output in workflow.run_stream(initial_state):
            print(f"\n[节点: {node_name}]")
            if node_output:
                if "messages" in node_output and node_output["messages"]:
                    last_msg = node_output["messages"][-1]
                    if hasattr(last_msg, 'content'):
                        print(f"  消息: {last_msg.content[:200]}..." if len(last_msg.content) > 200 else f"  消息: {last_msg.content}")
                
                if "collected_data" in node_output:
                    data = node_output["collected_data"]
                    if data:
                        if isinstance(data, dict):
                            print(f"  收集数据: {list(data.keys())}")
                        else:
                            print(f"  收集数据: {type(data).__name__}, 长度: {len(data) if hasattr(data, '__len__') else 'N/A'}")
                
                if "charts" in node_output:
                    charts = node_output["charts"]
                    print(f"  图表数量: {len(charts)}")
                    if charts:
                        for chart in charts:
                            print(f"    - {chart}")
                
                if "answer" in node_output and node_output["answer"]:
                    print(f"\n{'='*60}")
                    print("最终回答 (answer):")
                    print(f"{'='*60}")
                    print(node_output["answer"])
                    
                    final_charts = node_output.get("charts", [])
                    if final_charts:
                        print(f"\n生成的图表:")
                        for chart in final_charts:
                            if isinstance(chart, dict) and "path" in chart:
                                print(f"  - {chart['path']}")
                            else:
                                print(f"  - {chart}")
                
                if "report" in node_output and node_output["report"]:
                    print(f"\n{'='*60}")
                    print("报告内容 (report):")
                    print(f"{'='*60}")
                    print(node_output["report"])
                    
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_moutai_report())
