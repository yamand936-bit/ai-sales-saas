import os

ROUTER_FILE = r'src\merchant\router.py'
SERVICE_FILE = r'src\merchant\service.py'

def modify_service():
    methods = """
    @staticmethod
    def toggle_conversation_human_mode(conversation_id: int):
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter_by(id=conversation_id).first()
            if conv:
                conv.requires_human = not conv.requires_human
                db.commit()
                return conv
        finally:
            db.close()

    @staticmethod
    def resolve_conversation(conversation_id: int):
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter_by(id=conversation_id).first()
            if conv:
                conv.requires_human = False
                db.commit()
                return conv
        finally:
            db.close()

    @staticmethod
    def update_conversation_context(conversation_id: int, context: str):
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter_by(id=conversation_id).first()
            if conv:
                conv.context = context
                db.commit()
                return conv
        finally:
            db.close()
"""
    with open(SERVICE_FILE, 'a', encoding='utf-8') as f:
        f.write(methods)

def clean_router():
    with open(ROUTER_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    out_lines = []
    
    # Simple state machine to drop empty try-finally blocks that only contained db = SessionLocal and db.close
    i = 0
    while i < len(lines):
        line = lines[i]
        
        if line.strip() == "from src.core.database import SessionLocal":
            i += 1
            continue
            
        if line.strip() == "db = SessionLocal()":
            i += 1
            # Check if next line is try:
            if i < len(lines) and lines[i].strip() == "try:":
                i += 1
            continue
            
        if line.strip() == "db.close()":
            # Check if previous line was finally: (meaning we should delete the finally: too if we track back)
            # Since we iterate sequentially, if we encounter db.close(), we drop it.
            # We also need to drop "finally:" if it sits right before db.close() and nothing else inside it.
            if out_lines and out_lines[-1].strip() == "finally:":
                out_lines.pop()
            i += 1
            continue
            
        if "conv.requires_human = not conv.requires_human" in line:
            indent = line[:len(line) - len(line.lstrip())]
            out_lines.append(indent + "MerchantService.toggle_conversation_human_mode(conv.id)\n")
            i += 1
            # Drop the db.commit that follows
            if i < len(lines) and lines[i].strip() == "db.commit()":
                i += 1
            continue
            
        if "conv.requires_human = False" in line:
            indent = line[:len(line) - len(line.lstrip())]
            out_lines.append(indent + "MerchantService.resolve_conversation(conv.id)\n")
            i += 1
            # Drop following db.commit() if any in this block
            # In merchant_reply, db.commit() is outside the if block.
            continue
            
        if "conv.context = json.dumps(ctx)" in line:
            indent = line[:len(line) - len(line.lstrip())]
            out_lines.append(indent + "MerchantService.update_conversation_context(conv.id, json.dumps(ctx))\n")
            i += 1
            if i < len(lines) and lines[i].strip() == "db.commit()":
                i += 1
            continue

        if line.strip() == "db.commit()":
            # Any remaining db.commit drops
            i += 1
            continue

        out_lines.append(line)
        i += 1

    # In Python, since we dropped `try:` and `finally:`, the indentation for what was inside `try:` might now be 4 spaces too deep. 
    # But Python accepts overly indented blocks as long as they are uniformly indented. Wait, no, it will throw `IndentationError: unexpected indent`.
    # Let me just properly rewrite those specific handlers!
    # A script to blindly drop `try:` and its indentation is risky. 

    # Wait, instead of this complex regex, let me write targeted string replacements!
    pass

if __name__ == "__main__":
    pass
