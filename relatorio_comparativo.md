# Relatório Comparativo de Bancos de Dados: PostgreSQL, MongoDB e Cassandra

Este documento apresenta a modelagem e a análise de performance entre PostgreSQL (Relacional), MongoDB (Orientado a Documentos) e Cassandra (Colunar) utilizando o dataset `vendas.csv` (aprox. 93 mil registros).

## 1. Modelagem de Dados

### 1.1 PostgreSQL (Modelo Normalizado)
Foi adotado um modelo relacional normalizado para avaliar o custo de `JOIN`s nas consultas analíticas.

**Tabelas:**
```sql
CREATE TABLE lojas (id_loja VARCHAR(255) PRIMARY KEY);
CREATE TABLE produtos (produto VARCHAR(255) PRIMARY KEY);
CREATE TABLE vendas (codigo_venda INT PRIMARY KEY, data DATE, id_loja VARCHAR(255) REFERENCES lojas(id_loja));
CREATE TABLE itens_venda (
    id SERIAL PRIMARY KEY,
    codigo_venda INT REFERENCES vendas(codigo_venda),
    produto VARCHAR(255) REFERENCES produtos(produto),
    quantidade INT,
    valor_unitario DECIMAL(10, 2),
    valor_final DECIMAL(10, 2)
);
```

### 1.2 MongoDB (Modelo de Documentos Aninhados)
Para o MongoDB, os itens de venda foram aninhados dentro de um único documento de `venda`, explorando o conceito de *Aggregate Pattern* do NoSQL.

**Estrutura do Documento (Coleção `vendas`):**
```json
{
  "_id": ObjectId("..."),
  "codigo_venda": 1,
  "data": "2019-01-01",
  "id_loja": "Iguatemi Esplanada",
  "itens": [
    { "produto": "Sapato Estampa", "quantidade": 1, "valor_unitario": 358.0, "valor_final": 358.0 },
    { "produto": "Camiseta", "quantidade": 2, "valor_unitario": 180.0, "valor_final": 360.0 }
  ]
}
```

### 1.3 Cassandra (Modelo Query-Driven e Wide Column)
No Cassandra, os dados foram denormalizados de acordo com as consultas a serem realizadas. Utilizamos `Counters` para agregações globais.

**Tabelas:**
```sql
-- Para busca por venda
CREATE TABLE vendas_por_codigo (
    codigo_venda int, id_item timeuuid, data date, id_loja text, produto text,
    quantidade int, valor_unitario float, valor_final float,
    PRIMARY KEY ((codigo_venda), id_item)
);

-- Para faturamento por loja
CREATE TABLE faturamento_por_loja (
    id_loja text, codigo_venda int, id_item timeuuid, data date, produto text,
    quantidade int, valor_unitario float, valor_final float,
    PRIMARY KEY ((id_loja), codigo_venda, id_item)
);

-- Para total de produtos vendidos (Tabela de Counter)
CREATE TABLE produtos_mais_vendidos (
    produto text PRIMARY KEY,
    quantidade_total counter
);
```

---

## 2. Consultas Executadas e Resultados Esperados

### Query 1: Operacional (Buscar itens de uma venda específica, ex: 500)
- **Postgres:** `SELECT * FROM itens_venda WHERE codigo_venda = 500`
- **Mongo:** `db.vendas.find({"codigo_venda": 500})`
- **Cassandra:** `SELECT * FROM vendas_por_codigo WHERE codigo_venda = 500`

**Resultado Esperado:** Uma lista dos itens contendo `produto`, `quantidade`, `valor_unitario` e `valor_final` vendidos sob aquele código.

### Query 2: Analítica 1 (Faturamento Total por Loja)
- **Postgres:** `SELECT v.id_loja, SUM(i.valor_final) FROM itens_venda i JOIN vendas v ON i.codigo_venda = v.codigo_venda GROUP BY v.id_loja`
- **Mongo:** `db.vendas.aggregate([{"$unwind": "$itens"}, {"$group": {"_id": "$id_loja", "faturamento": {"$sum": "$itens.valor_final"}}}])`
- **Cassandra:** Para cada loja: `SELECT SUM(valor_final) FROM faturamento_por_loja WHERE id_loja = ?`

**Resultado Esperado:**
`[('Iguatemi Esplanada', 150000.50), ('Norte Shopping', 123456.00), ...]`

### Query 3: Analítica 2 (Top 5 Produtos mais vendidos em quantidade)
- **Postgres:** `SELECT produto, SUM(quantidade) FROM itens_venda GROUP BY produto ORDER BY SUM(quantidade) DESC LIMIT 5`
- **Mongo:** `db.vendas.aggregate([{"$unwind": "$itens"}, {"$group": {"_id": "$itens.produto", "quantidade": {"$sum": "$itens.quantidade"}}}, {"$sort": {"quantidade": -1}}, {"$limit": 5}])`
- **Cassandra:** `SELECT produto, quantidade_total FROM produtos_mais_vendidos`, sendo a ordenação e limitação (top 5) processada no lado do cliente (em memória).

**Resultado Esperado:**
`[('Bermuda Liso', 1245), ('Tênis Xadrez', 980), ...]`

---

## 3. Avaliação de Performance (Resultados)

Abaixo estão os resultados cronometrados da ingestão de 93.910 registros e do tempo de execução de consultas a frio.

### Tempo de Persistência (Carga de Dados)
- **PostgreSQL:** `2.55s` (Liderou graças ao insert em batch com `executemany`)
- **MongoDB:** `11.94s` (Intermediário, afetado pelo processo do Pandas de agrupar em documentos aninhados antes da inserção)
- **Cassandra:** `24.37s` (Mais demorado, pois cada linha teve que ser inserida em múltiplas tabelas concorrentemente, denormalizando os dados)

### Tempo de Consulta (Queries)
| Banco de Dados | Query Operacional | Analítica 1 (Faturamento) | Analítica 2 (Top 5 Produtos) |
|----------------|-------------------|---------------------------|------------------------------|
| **PostgreSQL** | 0.0209 s          | 0.0342 s                  | 0.0093 s                     |
| **MongoDB**    | 0.0060 s          | 0.0551 s                  | 0.0397 s                     |
| **Cassandra**  | **0.0041 s**      | 0.1869 s                  | **0.0074 s**                 |

### Conclusão e Observações
- **Leitura Operacional (Pontual):** O **Cassandra** e **MongoDB** sobressaíram com tempos excelentes. O Cassandra obteve a melhor marca (`0.0041s`), pois acessa a partição exata da query. O Mongo (`0.0060s`) é muito rápido pois traz a venda inteira num único documento indexado.
- **Leitura Analítica:** O **PostgreSQL** lidou muito bem com agregações completas. O Mongo foi um pouco mais lento pelo `$unwind`. Já o Cassandra foi rápido para agregação de Counter (`0.0074s`), mas muito lento para percorrer várias partições e somar os valores (Analítica 1: `0.1869s`), já que seu forte não é o *full table scan*.

*(Ambiente de Testes: Mac OS Local, Containers via Docker, Scripts em Python 3.10)*
