import time
import json
import psycopg2
from pymongo import MongoClient
from cassandra.cluster import Cluster

def run_postgres_queries():
    conn = psycopg2.connect(
        dbname="tbd_vendas", user="admin", password="password", host="localhost", port="5432"
    )
    cur = conn.cursor()
    
    # 1. Operational: Fetch items for a sale
    start = time.time()
    cur.execute("SELECT * FROM itens_venda WHERE codigo_venda = %s", (500,))
    _ = cur.fetchall()
    op_time = time.time() - start
    
    # 2. Analytical 1: Total Revenue by Store
    start = time.time()
    cur.execute("""
        SELECT v.id_loja, SUM(i.valor_final) 
        FROM itens_venda i 
        JOIN vendas v ON i.codigo_venda = v.codigo_venda 
        GROUP BY v.id_loja
    """)
    _ = cur.fetchall()
    an1_time = time.time() - start
    
    # 3. Analytical 2: Top 5 Products
    start = time.time()
    cur.execute("""
        SELECT produto, SUM(quantidade) 
        FROM itens_venda 
        GROUP BY produto 
        ORDER BY SUM(quantidade) DESC 
        LIMIT 5
    """)
    _ = cur.fetchall()
    an2_time = time.time() - start
    
    cur.close()
    conn.close()
    return op_time, an1_time, an2_time

def run_mongo_queries():
    client = MongoClient("mongodb://admin:password@localhost:27017/")
    db = client["tbd_vendas"]
    colecao = db["vendas"]
    
    # 1. Operational
    start = time.time()
    _ = list(colecao.find({"codigo_venda": 500}))
    op_time = time.time() - start
    
    # 2. Analytical 1
    start = time.time()
    pipeline1 = [
        {"$unwind": "$itens"},
        {"$group": {"_id": "$id_loja", "faturamento": {"$sum": "$itens.valor_final"}}}
    ]
    _ = list(colecao.aggregate(pipeline1))
    an1_time = time.time() - start
    
    # 3. Analytical 2
    start = time.time()
    pipeline2 = [
        {"$unwind": "$itens"},
        {"$group": {"_id": "$itens.produto", "quantidade": {"$sum": "$itens.quantidade"}}},
        {"$sort": {"quantidade": -1}},
        {"$limit": 5}
    ]
    _ = list(colecao.aggregate(pipeline2))
    an2_time = time.time() - start
    
    client.close()
    return op_time, an1_time, an2_time

def run_cassandra_queries(lojas):
    cluster = Cluster(['localhost'], port=9042)
    session = cluster.connect('tbd_vendas')
    
    # 1. Operational
    start = time.time()
    _ = list(session.execute("SELECT * FROM vendas_por_codigo WHERE codigo_venda = %s", (500,)))
    op_time = time.time() - start
    
    # 2. Analytical 1: Query each store partition
    start = time.time()
    for loja in lojas:
        # Cassandra 4 supports SUM() over a partition
        _ = list(session.execute("SELECT SUM(valor_final) FROM faturamento_por_loja WHERE id_loja = %s", (loja,)))
    an1_time = time.time() - start
    
    # 3. Analytical 2: Scan counters and sort
    start = time.time()
    rows = session.execute("SELECT produto, quantidade_total FROM produtos_mais_vendidos")
    produtos = [{"produto": r.produto, "qtde": r.quantidade_total} for r in rows]
    produtos.sort(key=lambda x: x["qtde"], reverse=True)
    top_5 = produtos[:5]
    an2_time = time.time() - start
    
    cluster.shutdown()
    return op_time, an1_time, an2_time

if __name__ == "__main__":
    import pandas as pd
    df = pd.read_csv("vendas.csv")
    lojas_unicas = df['id_loja'].unique().tolist()
    
    print("Executando Postgres...")
    pg_op, pg_a1, pg_a2 = run_postgres_queries()
    
    print("Executando Mongo...")
    mg_op, mg_a1, mg_a2 = run_mongo_queries()
    
    print("Executando Cassandra...")
    cs_op, cs_a1, cs_a2 = run_cassandra_queries(lojas_unicas)
    
    resultados = {
        "postgres": {"operacional": pg_op, "analitica_1": pg_a1, "analitica_2": pg_a2},
        "mongodb": {"operacional": mg_op, "analitica_1": mg_a1, "analitica_2": mg_a2},
        "cassandra": {"operacional": cs_op, "analitica_1": cs_a1, "analitica_2": cs_a2}
    }
    
    with open("resultados_queries.json", "w") as f:
        json.dump(resultados, f, indent=4)
        
    print("Testes concluídos!")
    for db, res in resultados.items():
        print(f"[{db.upper()}] OP: {res['operacional']:.4f}s | AN1: {res['analitica_1']:.4f}s | AN2: {res['analitica_2']:.4f}s")
