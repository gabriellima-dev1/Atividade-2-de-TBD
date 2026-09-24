CREATE KEYSPACE IF NOT EXISTS tbd_vendas WITH replication = {'class':'SimpleStrategy', 'replication_factor':1};

USE tbd_vendas;

-- Tabela para query operacional (busca por código da venda)
CREATE TABLE IF NOT EXISTS vendas_por_codigo (
    codigo_venda int,
    id_item timeuuid,
    data date,
    id_loja text,
    produto text,
    quantidade int,
    valor_unitario float,
    valor_final float,
    PRIMARY KEY ((codigo_venda), id_item)
);

-- Tabela para query analítica 1 (Faturamento por loja)
CREATE TABLE IF NOT EXISTS faturamento_por_loja (
    id_loja text,
    codigo_venda int,
    id_item timeuuid,
    data date,
    produto text,
    quantidade int,
    valor_unitario float,
    valor_final float,
    PRIMARY KEY ((id_loja), codigo_venda, id_item)
);

-- Tabela (Counter) para query analítica 2 (Top 5 produtos)
CREATE TABLE IF NOT EXISTS produtos_mais_vendidos (
    produto text PRIMARY KEY,
    quantidade_total counter
);
