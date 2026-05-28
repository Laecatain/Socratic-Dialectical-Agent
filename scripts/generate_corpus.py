"""Batch corpus generator - 9 schools x 6 entries = 54 total"""
import json
import os
import sys
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

load_dotenv()

class SingleCorpusSchema(BaseModel):
    text_id: str
    category: str
    text_type: str
    content: str
    source_reference: str

CORPUS_MATRIX = [
    {"cat": "分配正义", "src": "罗尔斯正义论", "opp": "诺齐克自我所有权/张伯伦税收实验", "n_c": 4, "n_cl": 2},
    {"cat": "程序正义", "src": "诺齐克无政府国家与乌托邦", "opp": "罗尔斯历史不正义积累/天赋彩票", "n_c": 4, "n_cl": 2},
    {"cat": "功利主义", "src": "边沁/密尔功利主义", "opp": "道义论个体权利/德沃金权利作为王牌", "n_c": 4, "n_cl": 2},
    {"cat": "道义论", "src": "康德道德形而上学原理", "opp": "功利主义后果论/定时炸弹酷刑困境", "n_c": 4, "n_cl": 2},
    {"cat": "资格理论", "src": "诺齐克资格理论", "opp": "罗尔斯差异原则/起点不公平的道义债务", "n_c": 4, "n_cl": 2},
    {"cat": "运气平等主义", "src": "德沃金/科亨运气平等", "opp": "对粗心受害者不救助的残酷性/安德森批判", "n_c": 4, "n_cl": 2},
    {"cat": "社群主义", "src": "桑德尔/麦金泰尔社群主义", "opp": "原子化个人侵蚀共同体/消极自由剥夺", "n_c": 4, "n_cl": 2},
    {"cat": "能力进路", "src": "森/努斯鲍姆能力进路", "opp": "家长制越权/能力清单文化帝国主义", "n_c": 4, "n_cl": 2},
]

GEN_SYSTEM = "You are a scholar of Western political philosophy. Generate counter_example or claim for the specified school. Each entry 150-200 Chinese characters. Include concrete thought experiments or logical flaw analysis. source_reference MUST cite real philosophers and real works. Output pure JSON array, no markdown wrapping."

GEN_HUMAN = "School: {cat} | Source: {src} | Opponent direction: {opp}\nGenerate text_type={ttype} #{idx}, text_id=CORPUS_{gid:03d}"

def main():
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    model = os.getenv("OPENAI_MODEL_NAME", "deepseek-v4-flash")
    if not api_key:
        sys.exit("No OPENAI_API_KEY")
    llm = ChatOpenAI(model=model, api_key=api_key, base_url=api_base, temperature=0.7)
    prompt = ChatPromptTemplate.from_messages([("system", GEN_SYSTEM), ("human", GEN_HUMAN)])
    chain = prompt | llm
    all_entries = []
    gid = 1
    for spec in CORPUS_MATRIX:
        for i in range(spec["n_c"]):
            try:
                resp = chain.invoke({"cat": spec["cat"], "src": spec["src"], "opp": spec["opp"], "ttype": "counter_example", "idx": i+1, "gid": gid})
                text = resp.content.strip()
                if "```" in text:
                    text = text.split("```")[1].replace("json", "").strip()
                entry = json.loads(text)
                if isinstance(entry, list):
                    entry = entry[0]
                entry["text_id"] = f"CORPUS_{gid:03d}"
                entry["category"] = spec["cat"]
                entry["text_type"] = "counter_example"
                all_entries.append(entry)
                print(f"OK {entry['text_id']} {spec['cat']} counter_example")
                gid += 1
            except Exception as e:
                print(f"FAIL {spec['cat']} counter_example #{i+1}: {e}")
        for i in range(spec["n_cl"]):
            try:
                resp = chain.invoke({"cat": spec["cat"], "src": spec["src"], "opp": spec["opp"], "ttype": "claim", "idx": i+1, "gid": gid})
                text = resp.content.strip()
                if "```" in text:
                    text = text.split("```")[1].replace("json", "").strip()
                entry = json.loads(text)
                if isinstance(entry, list):
                    entry = entry[0]
                entry["text_id"] = f"CORPUS_{gid:03d}"
                entry["category"] = spec["cat"]
                entry["text_type"] = "claim"
                all_entries.append(entry)
                print(f"OK {entry['text_id']} {spec['cat']} claim")
                gid += 1
            except Exception as e:
                print(f"FAIL {spec['cat']} claim #{i+1}: {e}")
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "generated_corpus.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)
    print(f"\nDone: {len(all_entries)} entries -> {out_path}")
    print("Next: python ingest.py")

if __name__ == "__main__":
    main()