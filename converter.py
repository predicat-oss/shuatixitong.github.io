from docx import Document
import re
import json
import os

# ================== 配置区域 ==================
INPUT_FILE = "maogai.docx"
OUTPUT_FILE = "quiz_data.js"
UNIT_SIZE = 80  # 每个模块的标准题目数

# ================== 核心解析逻辑 ==================
def parse_docx(filename):
    if not os.path.exists(filename):
        print(f"❌ 错误：找不到文件 {filename}")
        return {}

    print(f"📂 正在深度解析文档: {filename} ...")
    doc = Document(filename)
    
    # 临时存储所有识别到的题目
    raw_questions = []
    
    # 正则表达式
    # 匹配题目：支持 "1." "1、" "1 " 等
    re_q_start = re.compile(r"^\s*(\d+)[\.．、\s]\s*(.*)")
    # 匹配判断题：支持 "对 1." 或 "1. 对"
    re_judge_start = re.compile(r"^\s*(对|错)\s*(\d+)[\.．、\s]\s*(.*)")
    # 匹配选项： A. B. C. D.
    re_option = re.compile(r"^\s*([A-D])[\.．、\s]\s*(.*)")
    # 匹配答案： (A) （A）
    re_answer = re.compile(r"[（\(]\s*([A-D]+)\s*[）\)]")

    current_q = None
    
    # 1. 第一次遍历：提取所有能识别的题目
    for para in doc.paragraphs:
        text = para.text.strip().replace("　", " ")
        if not text: continue

        # --- 判断题识别 ---
        judge_match = re_judge_start.match(text)
        if judge_match:
            if current_q: raw_questions.append(current_q)
            ans_char = "A" if judge_match.group(1) == "对" else "B"
            current_q = {
                "orig_id": int(judge_match.group(2)), # 原始题号
                "type": "判断题",
                "question": judge_match.group(3),
                "options": ["A. 正确", "B. 错误"],
                "answer": ans_char
            }
            continue

        # --- 选择题识别 ---
        q_match = re_q_start.match(text)
        if q_match:
            # 排除选项误判 (如有些选项写 1. 2.)
            if not re_option.match(text):
                if current_q: raw_questions.append(current_q)
                
                q_id = int(q_match.group(1))
                content = q_match.group(2)
                
                # 提取答案并挖空
                found_ans = ""
                ans_search = re_answer.search(content)
                if ans_search:
                    found_ans = ans_search.group(1)
                    content = re_answer.sub("（ ）", content)
                
                current_q = {
                    "orig_id": q_id,
                    "type": "单选题", # 默认为单选，后续修正
                    "question": content,
                    "options": [],
                    "answer": found_ans
                }
                continue

        # --- 选项识别 ---
        opt_match = re_option.match(text)
        if current_q and opt_match:
            # 只有当选项看起来属于当前题目时才添加
            # 防止误把下一题的题干当成选项
            if not re_q_start.match(text):
                current_q["options"].append(f"{opt_match.group(1)}. {opt_match.group(2)}")

    if current_q: raw_questions.append(current_q)

    # 2. 第二次处理：智能分单元与补全
    # 我们知道每个单元有80题。我们根据 orig_id 来判断它属于哪个单元。
    # 比如 orig_id = 1，那就是新单元的开始。
    
    final_modules = {}
    current_unit_idx = 1
    current_unit_qs = []
    
    # 辅助函数：保存当前单元
    def save_unit():
        nonlocal current_unit_qs, current_unit_idx
        if not current_unit_qs: return
        
        # 补全缺失的题目 (1-80)
        # 创建一个映射表
        id_map = {q['orig_id']: q for q in current_unit_qs}
        full_unit = []
        
        for i in range(1, UNIT_SIZE + 1):
            if i in id_map:
                q = id_map[i]
                # 修正多选题类型
                if len(q['answer']) > 1: q['type'] = "多选题"
                # 修正无选项的选择题（可能是判断题误判）
                if not q['options'] and q['answer'] in ['A', 'B']:
                    q['type'] = "判断题"
                    q['options'] = ["A. 正确", "B. 错误"]
                
                # 统一重新编号 ID，方便前端 grid 使用
                q['id'] = i 
                full_unit.append(q)
            else:
                # ⚠ 发现缺失题目，自动补全占位符
                print(f"⚠️ 第 {current_unit_idx} 单元 缺失第 {i} 题，已自动补全占位。")
                full_unit.append({
                    "id": i,
                    "orig_id": i,
                    "type": "未知",
                    "question": f"【原文档缺失第 {i} 题】请核对Word文档...",
                    "options": ["A. 题目缺失", "B. 题目缺失"],
                    "answer": ""
                })
        
        title = f"第 {current_unit_idx} 套模拟卷 (1-80)"
        final_modules[title] = full_unit
        current_unit_idx += 1
        current_unit_qs = []

    # 遍历识别到的题目进行分组
    for q in raw_questions:
        # 如果遇到 1 号题，且当前暂存区已有数据，说明进入了新单元
        if q['orig_id'] == 1 and len(current_unit_qs) > 0:
            save_unit()
        
        # 过滤掉大于80的异常题号
        if q['orig_id'] <= 80:
            current_unit_qs.append(q)
            
    # 保存最后一个单元
    save_unit()

    return final_modules

# ================== 导出 JS ==================
def export_js(data):
    print(f"💾 正在写入 {OUTPUT_FILE} ...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("const QUIZ_DATA = ")
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write(";")
    
    total_q = sum(len(v) for v in data.values())
    print(f"✅ 处理完成！共生成 {len(data)} 个单元，总计 {total_q} 题（含自动补全的空题）。")

if __name__ == "__main__":
    data = parse_docx(INPUT_FILE)
    if data:
        export_js(data)