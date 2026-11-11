SAMPLES = [
    {"name": "取り込む", "props": {"kind": "finish", "id": "12", "base": "main"}},
    {"name": "取り込む（中間提出）", "props": {"kind": "finish", "id": "12", "base": "main", "partial": True}},
    {"name": "完了にする", "props": {"kind": "complete", "id": "12", "base": "main", "submitted": True}},
    {"name": "承認して取り込む", "props": {"kind": "approve", "id": "20", "base": "develop"}},
    {"name": "差し戻す", "props": {"kind": "reject", "id": "20"}},
    {"name": "反映", "props": {"kind": "apply", "id": "12", "base": "main"}},
    {"name": "コメント", "props": {"kind": "comment", "id": "20"}},
    {"name": "提出", "props": {"kind": "submit", "base": "main"}},
    {"name": "ブランチの提出を取り込む", "props": {"kind": "merge", "id": "develop"}},
]
