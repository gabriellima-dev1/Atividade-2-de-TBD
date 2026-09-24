import pandas as pd
import time
import uuid
import json

# DB Drivers
import psycopg2
from psycopg2.extras import execute_batch
from pymongo import MongoClient
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args

def ingest_postgres(df):
    conn = psycopg2.connect(
        dbname="tbd_vendas", user="admin", password="password", host="localhost", port="5432"
    )
    cur = conn.cursor()
    
    cur.execute("TRUNCATE TABLE itens_venda, vendas, produtos, lojas RESTART IDENTITY;")
    
    # 1. Insert Lojas
    lojas = df[['id_loja']].drop_duplicates().values.tolist()
    execute_batch(cur, "INSERT INTO lojas (id_loja) VALUES (%s) ON CONFLICT DO NOTHING", lojas)
    
    # 2. Insert Produtos
    produtos = df[['produto']].drop_duplicates().values.tolist()
    execute_batch(cur, "INSERT INTO produtos (produto) VALUES (%s) ON CONFLICT DO NOTHING", produtos)
    
    # 3. Insert Vendas
    vendas = df[['codigo_venda', 'data', 'id_loja']].drop_duplicates().values.tolist()
    execute_batch(cur, "INSERT INTO vendas (codigo_venda, data, id_loja) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", vendas)
    
    # 4. Insert Itens Venda
    itens = df[['codigo_venda', 'produto', 'quantidade', 'valor_unitario', 'valor_final']].values.tolist()
    execute_batch(cur, """
        INSERT INTO itens_venda (codigo_venda, produto, quantidade, valor_unitario, valor_final) 
        VALUES (%s, %s, %s, %s, %s)
    """, itens)
    
    conn.commit()
    cur.close()
    conn.close()

def ingest_mongo(df):
    client = MongoClient("mongodb://admin:password@localhost:27017/")
    db = client["tbd_vendas"]
    colecao = db["vendas"]
    colecao.drop()  # Drop to start fresh
    
    # Re-create indices since we dropped the collection
    colecao.create_index("codigo_venda", unique=True)
    colecao.create_index("id_loja")
    colecao.create_index("itens.produto")
    
    # Group by codigo_venda ONLY to avoid unique key violation (due to dataset inconsistencies)
    docs = []
    grouped = df.groupby('codigo_venda')
    for codigo_venda, group in grouped:
        data = group['data'].iloc[0]
        id_loja = group['id_loja'].iloc[0]
        itens = group[['produto', 'quantidade', 'valor_unitario', 'valor_final']].to_dict('records')
        doc = {
            "codigo_venda": int(codigo_venda),
            "data": str(data)[:10],
            "id_loja": id_loja,
            "itens": itens
        }
        docs.append(doc)
        
    colecao.insert_many(docs)
    client.close()

def ingest_cassandra(df):
    cluster = Cluster(['localhost'], port=9042)
    session = cluster.connect('tbd_vendas')
    
    # Truncate tables to avoid duplicates
    session.execute("TRUNCATE vendas_por_codigo")
    session.execute("TRUNCATE faturamento_por_loja")
    session.execute("TRUNCATE produtos_mais_vendidos")
    
    prep_vendas_por_codigo = session.prepare("""
        INSERT INTO vendas_por_codigo (codigo_venda, id_item, data, id_loja, produto, quantidade, valor_unitario, valor_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """)
    prep_faturamento_por_loja = session.prepare("""
        INSERT INTO faturamento_por_loja (id_loja, codigo_venda, id_item, data, produto, quantidade, valor_unitario, valor_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """)
    prep_produtos_mais_vendidos = session.prepare("""
        UPDATE produtos_mais_vendidos SET quantidade_total = quantidade_total + ? WHERE produto = ?
    """)

    # We need to insert row by row (or async) since Cassandra doesn't do large batches well.
    # We will use execute_concurrent_with_args
    args_vendas_codigo = []
    args_faturamento_loja = []
    args_produtos = []
    
    for _, row in df.iterrows():
        item_id = uuid.uuid1()
        data_str = str(row['data'])[:10]
        
        args_vendas_codigo.append((
            int(row['codigo_venda']), item_id, data_str, row['id_loja'], row['produto'],
            int(row['quantidade']), float(row['valor_unitario']), float(row['valor_final'])
        ))
        
        args_faturamento_loja.append((
            row['id_loja'], int(row['codigo_venda']), item_id, data_str, row['produto'],
            int(row['quantidade']), float(row['valor_unitario']), float(row['valor_final'])
        ))
        
        args_produtos.append((int(row['quantidade']), row['produto']))
        
    execute_concurrent_with_args(session, prep_vendas_por_codigo, args_vendas_codigo, concurrency=100)
    execute_concurrent_with_args(session, prep_faturamento_por_loja, args_faturamento_loja, concurrency=100)
    execute_concurrent_with_args(session, prep_produtos_mais_vendidos, args_produtos, concurrency=100)
    
    cluster.shutdown()

if __name__ == "__main__":
    print("Lendo CSV...")
    df = pd.read_csv("vendas.csv")
    print(f"Total de registros: {len(df)}")
    
    resultados = {}
    
    print("Ingerindo no Postgres...")
    start = time.time()
    ingest_postgres(df)
    end = time.time()
    resultados['postgres'] = end - start
    print(f"Postgres finalizado: {resultados['postgres']:.2f} s")
    
    print("Ingerindo no MongoDB...")
    start = time.time()
    ingest_mongo(df)
    end = time.time()
    resultados['mongodb'] = end - start
    print(f"MongoDB finalizado: {resultados['mongodb']:.2f} s")
    
    print("Ingerindo no Cassandra...")
    start = time.time()
    ingest_cassandra(df)
    end = time.time()
    resultados['cassandra'] = end - start
    print(f"Cassandra finalizado: {resultados['cassandra']:.2f} s")
    
    with open("resultados_ingestao.json", "w") as f:
        json.dump(resultados, f, indent=4)
        
    print("Concluído!")
