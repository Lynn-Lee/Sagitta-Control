#!/usr/bin/env python3
"""
Archery 1.x → 2.0 数据迁移脚本（Sprint 6）。

用法：
  python3 migrate_from_archery1x.py \
    --src-host 127.0.0.1 --src-port 3306 \
    --src-user archery --src-pass archery \
    --src-db archery \
    --dst-url postgresql+psycopg2://sagitta:sagitta123@localhost:5432/sagitta_control \
    --dry-run
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--src-host", default="127.0.0.1")
    p.add_argument("--src-port", type=int, default=3306)
    p.add_argument("--src-user", default="archery")
    p.add_argument("--src-pass", default="archery")
    p.add_argument("--src-db", default="archery")
    p.add_argument("--dst-url", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--tables", default="all")
    return p.parse_args()

STATUS_MAP = {
    "workflow_manreviewing": 0, "workflow_autoreviewwrong": 1,
    "workflow_review_pass": 2, "workflow_timingtask": 3,
    "workflow_queuing": 4, "workflow_executing": 5,
    "workflow_finish": 6, "workflow_exception": 7, "workflow_abort": 8,
}

def migrate_users(src, dst, dry):
    with src.cursor() as c:
        c.execute("SELECT id,username,password,email,first_name,last_name,is_superuser,is_active FROM auth_user")
        rows = c.fetchall()
    logger.info("用户：%d 条", len(rows))
    if dry: return len(rows)
    from sqlalchemy import text
    with dst.begin() as conn:
        for r in rows:
            display = f"{r['first_name']} {r['last_name']}".strip() or r['username']
            conn.execute(text("""INSERT INTO sql_users (username,password,display_name,email,is_superuser,is_active,auth_type,tenant_id)
                VALUES (:u,:p,:d,:e,:s,:a,'local',1) ON CONFLICT(username) DO NOTHING"""),
                {"u":r["username"],"p":r["password"],"d":display,"e":r["email"] or "","s":r["is_superuser"],"a":r["is_active"]})
    logger.info("✓ 用户迁移完成")
    return len(rows)

def migrate_resource_groups(src, dst, dry):
    with src.cursor() as c:
        c.execute("SELECT group_name,group_name_cn,ding_webhook FROM sql_resourcegroup")
        rows = c.fetchall()
    logger.info("资源组：%d 条", len(rows))
    if dry: return len(rows)
    from sqlalchemy import text
    with dst.begin() as conn:
        for r in rows:
            conn.execute(text("INSERT INTO resource_group(group_name,group_name_cn,ding_webhook,is_active,tenant_id) VALUES(:n,:c,:d,true,1) ON CONFLICT(group_name) DO NOTHING"),
                {"n":r["group_name"],"c":r["group_name_cn"] or "","d":r["ding_webhook"] or ""})
    logger.info("✓ 资源组迁移完成")
    return len(rows)

def migrate_instances(src, dst, dry):
    with src.cursor() as c:
        c.execute("SELECT instance_name,type,db_type,host,port,user,password,is_ssl,db_name,remark FROM sql_instance WHERE is_deleted=0")
        rows = c.fetchall()
    logger.info("实例：%d 条", len(rows))
    if dry: return len(rows)
    import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from sqlalchemy import text

    from app.core.security import encrypt_field
    with dst.begin() as conn:
        for r in rows:
            conn.execute(text("""INSERT INTO sql_instance(instance_name,type,db_type,mode,host,port,"user",password,is_ssl,db_name,remark,is_active,tenant_id)
                VALUES(:n,:t,:dt,'standalone',:h,:p,:u,:pw,:ssl,:db,:rm,true,1) ON CONFLICT(instance_name) DO NOTHING"""),
                {"n":r["instance_name"],"t":r["type"] or "master","dt":r["db_type"],"h":r["host"],"p":r["port"],
                 "u":encrypt_field(r["user"] or ""),"pw":encrypt_field(r["password"] or ""),"ssl":bool(r["is_ssl"]),
                 "db":r["db_name"] or "","rm":r["remark"] or ""})
    logger.info("✓ 实例迁移完成（密码已重新加密）")
    return len(rows)

def migrate_workflows(src, dst, dry):
    with src.cursor() as c:
        c.execute("""SELECT w.id,w.workflow_name,w.group_id,w.group_name,w.instance_id,w.db_name,
            w.syntax_type,w.is_backup,w.engineer,w.engineer_id,w.status,w.audit_auth_groups,
            w.finish_time,c.sql_content,c.review_content,c.execute_result
            FROM sql_workflow w LEFT JOIN sql_workflow_content c ON c.workflow_id=w.id LIMIT 10000""")
        rows = c.fetchall()
    logger.info("工单：%d 条", len(rows))
    if dry: return len(rows)
    from sqlalchemy import text
    with dst.begin() as conn:
        for r in rows:
            s = r.get("status","workflow_manreviewing")
            sint = STATUS_MAP.get(s,0) if isinstance(s,str) else int(s)
            conn.execute(text("""INSERT INTO sql_workflow(id,workflow_name,group_id,group_name,instance_id,db_name,
                syntax_type,is_backup,engineer,engineer_id,status,audit_auth_groups,finish_time,tenant_id)
                VALUES(:id,:n,:gid,:gn,:iid,:db,:sx,:bk,:eng,:eid,:st,:auths,:ft,1) ON CONFLICT(id) DO NOTHING"""),
                {"id":r["id"],"n":r["workflow_name"],"gid":r["group_id"],"gn":r["group_name"],"iid":r["instance_id"],
                 "db":r["db_name"],"sx":r.get("syntax_type",0),"bk":bool(r.get("is_backup",True)),
                 "eng":r["engineer"],"eid":r["engineer_id"],"st":sint,"auths":r.get("audit_auth_groups",""),"ft":r.get("finish_time")})
            if r.get("sql_content"):
                conn.execute(text("INSERT INTO sql_workflow_content(workflow_id,sql_content,review_content,execute_result,tenant_id) VALUES(:wid,:sql,:rv,:ex,1) ON CONFLICT(workflow_id) DO NOTHING"),
                    {"wid":r["id"],"sql":r.get("sql_content",""),"rv":r.get("review_content",""),"ex":r.get("execute_result","")})
    logger.info("✓ 工单迁移完成")
    return len(rows)

def main():
    args = parse_args()
    logger.info("Archery 1.x → 2.0 迁移 | dry_run=%s", args.dry_run)
    import pymysql
    from sqlalchemy import create_engine
    src = pymysql.connect(host=args.src_host, port=args.src_port, user=args.src_user,
        password=args.src_pass, db=args.src_db, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor)
    dst = create_engine(args.dst_url)
    tables = [t.strip() for t in args.tables.split(",")] if args.tables != "all" else ["users","resource_groups","instances","workflows"]
    fn_map = {"users":migrate_users,"resource_groups":migrate_resource_groups,"instances":migrate_instances,"workflows":migrate_workflows}
    total = {t: fn_map[t](src, dst, args.dry_run) for t in tables if t in fn_map}
    src.close()
    logger.info("完成：%s", total)

if __name__ == "__main__":
    main()
