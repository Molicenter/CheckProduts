# Consulta de Produto por Código de Barra

App Streamlit para usar durante visitas de loja: fotografa o código de barras
de um produto (câmera do celular/notebook) e mostra na hora, puxando do mesmo
banco Postgres do ERP usados nos outros apps: **código do produto, nome,
código de barra, estoque e preço de venda**.

Segue o mesmo padrão do `pedidos.py` que você me passou: mesma conexão
`st.connection("banco_erp", type="sql", ...)`, mesma view `python_estoque`
(a que já é usada em `buscar_estoque_erp`), mesma lista `LOJAS_NOMES` e o
mesmo mecanismo `ERP_ATIVO` do secrets para desligar a consulta se precisar.

## Como integrar no seu repositório

- Se seus outros apps já são páginas de um app multipágina (pasta `pages/`),
  salve este arquivo como `pages/📷_Consulta_Produto.py`.
- Se for um app avulso, basta rodar `streamlit run consulta_produto_barra.py`.
- Não precisa mexer no `secrets.toml`: ele reaproveita a conexão
  `[connections.banco_erp]` que os outros apps já usam.

## Dependências novas a adicionar

Este app usa leitura de código de barra por foto, que os outros apps ainda
não usam. Acrescente no `requirements.txt`:

```
opencv-python-headless
pyzbar
numpy
```

E crie (ou complete) o arquivo `packages.txt` na raiz do repositório com:

```
libzbar0
```

(`packages.txt` é como o Streamlit Community Cloud instala pacotes do sistema
operacional — aqui, a lib nativa que o `pyzbar` precisa para decodificar a
imagem. Sem isso o app ainda funciona, só cai para um leitor OpenCV nativo
mais fraco — ver abaixo.)

## Como a leitura funciona

1. Tenta ler com **pyzbar** (mais preciso, testado com EAN-13/UPC/Code128).
2. Se `pyzbar`/`libzbar0` não estiver disponível, cai para o detector nativo
   do **OpenCV** (`cv2.barcode.BarcodeDetector`) — funciona só com
   `pip install opencv-python-headless`, sem depender de lib de sistema, mas
   é menos robusto em fotos tortas ou com pouca luz.
3. Em qualquer caso, sempre há um campo de texto para digitar o código
   manualmente — útil se a foto não ler ou a etiqueta estiver danificada.

Testei localmente o caminho pyzbar (foto → decodificação → texto do código)
com um código EAN-13 gerado sinteticamente e decodificou corretamente.

## O que a tela mostra

Depois de ler ou digitar o código de barra e clicar em "Buscar produto":

- Nome do produto
- Código do produto (`cade_codigo`)
- Código de barra
- Estoque (da loja selecionada na barra lateral)
- Preço de venda

Se não achar o código exato, mostra sugestões de produtos com código de
barra parecido na mesma loja (útil quando o dígito verificador ou o formato
gravado no banco é ligeiramente diferente do lido na etiqueta).

Um histórico dos produtos consultados fica visível durante a sessão (some ao
fechar/recarregar a aba), com botão para limpar.

## Próximos passos possíveis (não incluídos ainda)

- Salvar o histórico de consultas no Supabase (como os outros apps fazem),
  para ficar disponível entre sessões/dispositivos.
- Buscar em todas as lojas de uma vez, em vez de selecionar uma por vez.

Me avisa se quiser que eu adicione algum desses.
