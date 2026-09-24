CREATE TABLE lojas (
    id_loja VARCHAR(255) PRIMARY KEY
);

CREATE TABLE produtos (
    produto VARCHAR(255) PRIMARY KEY
);

CREATE TABLE vendas (
    codigo_venda INT PRIMARY KEY,
    data DATE,
    id_loja VARCHAR(255) REFERENCES lojas(id_loja)
);

CREATE TABLE itens_venda (
    id SERIAL PRIMARY KEY,
    codigo_venda INT REFERENCES vendas(codigo_venda),
    produto VARCHAR(255) REFERENCES produtos(produto),
    quantidade INT,
    valor_unitario DECIMAL(10, 2),
    valor_final DECIMAL(10, 2)
);
