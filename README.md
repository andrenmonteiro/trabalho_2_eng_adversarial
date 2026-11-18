# Agentes adversariais para priorização de chamados

Protótipo acadêmico isolado do GLPI. Dois agentes Agno com objetivos conflitantes e modelo Gemini interagem por oito rodadas: o solicitante tenta obter atendimento rápido e o técnico tenta preservar uma fila justa. O simulador mantém o estado oficial, calcula consequências determinísticas e registra as decisões efetivamente produzidas pelo modelo.

## Guia passo a passo (Windows e PowerShell)

### 1. Extrair o ZIP

Baixe `adversarial-ticket-agents.zip` e use **Extrair Tudo**. Escolha `C:\` como destino. Como o ZIP já contém a pasta do projeto, os arquivos ficarão em `C:\adversarial-ticket-agents`. Abra o PowerShell nessa pasta ou navegue até ela:

```powershell
Set-Location "C:\adversarial-ticket-agents"
```

Confira que está no lugar certo:

```powershell
Get-Location
Get-ChildItem
```

Confirme que `pyproject.toml` está na pasta atual antes de continuar:

```powershell
Test-Path .\pyproject.toml
```

O resultado deve ser `True`. Todos os comandos abaixo são executados a partir de `C:\adversarial-ticket-agents`; o ambiente `.venv` e as dependências são criados dentro dessa pasta.

### 2. Verificar ou instalar Python

O projeto requer Python 3.12. Confira se o inicializador `py` está disponível:

```powershell
py -3.12 --version
```

Se o comando não encontrar o Python, instale-o pelo Windows Package Manager:

```powershell
winget install --id Python.Python.3.12 -e
```

Feche e abra o PowerShell novamente e repita `py -3.12 --version`. Se `winget` não estiver disponível, instale o Python 3.12 pelo [site oficial do Python](https://www.python.org/downloads/) e marque a opção de adicionar o Python ao `PATH` durante a instalação.

### 3. Criar o ambiente e instalar as dependências

Execute estes comandos dentro da pasta do projeto. Eles criam um ambiente virtual próprio e instalam Agno e o conector Gemini:

```powershell
py -3.12 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e .
```

Use o Python dentro de `.venv` nos próximos comandos. Assim não é preciso ativar o ambiente virtual nem alterar a política de execução do PowerShell.

### 4. Configurar a chave Gemini

Crie ou consulte uma chave no [Google AI Studio](https://aistudio.google.com/apikey). No mesmo PowerShell em que executará a simulação, configure a variável de ambiente:

```powershell
$env:GOOGLE_API_KEY = "cole-sua-chave-aqui"
```

A chave vale apenas para essa janela do PowerShell. Se abrir outra janela, configure-a novamente. Não coloque a chave no README, no código ou no ZIP.

O modelo principal é `gemini-3.5-flash-lite`; o modelo alternativo padrão é `gemini-3.8-flash`. Para selecionar outros modelos disponíveis para sua conta, configure `GEMINI_MODEL` ou `GEMINI_FALLBACK_MODEL` na mesma janela antes de executar:

```powershell
$env:GEMINI_MODEL = "gemini-3.5-flash-lite"
$env:GEMINI_FALLBACK_MODEL = "gemini-3.8-flash"
```

### 5. Executar

Inicie a simulação:

```powershell
& ".\.venv\Scripts\python.exe" -m adversarial_agents.cli
```

No menu, escolha `1` para oito chamados selecionados de um catálogo de 24 variações ou `2` para descrever um chamado manual. O cenário escolhe quatro tipos de incidente por execução e inclui duas ocorrências de cada descrição: uma de baixa criticidade e outra com gravidade variável. A seleção e a ordem mudam a cada execução, mantendo oito rodadas. No modo manual, escreva a descrição e informe a urgência e o impacto reais usando valores de 1 a 3. O solicitante selecionará os níveis que vai declarar; o técnico não verá os níveis reais.

O cenário padrão faz até 16 chamadas ao Gemini e pode levar alguns minutos. O simulador espera 12,5 segundos entre chamadas para respeitar cotas configuradas. Confira os limites da sua conta no painel do [Google AI Studio](https://aistudio.google.com/rate-limit). Se a API retornar erro `429` com `retryDelay`, aguarde o tempo informado antes de tentar novamente. Se sua cota permitir outra velocidade, ajuste `GEMINI_MIN_INTERVAL_SECONDS`.

### 6. (Opcional) Verificar regras sem chamar a API

Para executar as verificações offline, ainda dentro da pasta do projeto:

```powershell
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v
```

Essas verificações não precisam da chave Gemini. As decisões de teste usam agentes simulados e não fazem parte da demonstração.

## O que aparece na execução

A saída mostra a descrição do chamado, os níveis declarados, a estratégia identificada pelo simulador, a justificativa do solicitante, a decisão do técnico, as prioridades, as revisões e os efeitos sobre espera e reputação. Também mostra quando os níveis mudam em uma descrição repetida.

## Regras do cenário

- O catálogo contém oito tipos de chamados com três combinações de criticidade real cada. A cada execução, quatro tipos são selecionados; cada um aparece duas vezes, uma com criticidade baixa e outra com gravidade variável. Isso permite observar a mesma descrição em condições diferentes, com um conjunto e uma ordem que mudam entre execuções. O solicitante escolhe urgência e impacto separadamente, cada um entre 1 e 3; assim, pode declarar 3/3, 2/3, 1/1 ou outra combinação possível.
- O simulador distingue declaração honesta, meio inflada, inflada, subestimada e divergente, comparando os níveis numéricos com os reais. O modelo não decide esse rótulo por texto.
- Em ocorrências repetidas da mesma descrição, uma categoria estratégica ainda não usada rende +8 pontos de utilidade ao solicitante. Esse bônus incentiva a alternância entre honestidade, exagero parcial e exagero máximo, sem escolher a ação por ele.
- A prioridade usa o produto urgência × impacto: P1 a partir de 6, P2 a partir de 3, caso contrário P3.
- O agente técnico decide aceitar ou revisar. Uma revisão usa os níveis reais guardados pelo simulador e corrige a prioridade.
- Uma inflação confirmada por revisão reduz reputação em 20 pontos; uma declaração honesta aumenta em 5. Subestimar ou informar níveis diferentes é registrado como divergência, sem a penalidade por inflação. A reputação permanece entre 0 e 100.
- O sistema registra divergências não revisadas como alertas para a triagem seguinte. A espera simulada é 1 unidade para P1, 2 para P2 e 3 para P3.
- Cada revisão consome 1 unidade de esforço operacional, permitindo ao técnico ponderar custo e benefício ao escolher se investiga.
- O solicitante recebe uma tabela calculada pelo simulador com as nove combinações possíveis de urgência e impacto, prioridade, espera economizada e utilidade estimada. A estimativa considera +8 por unidade de espera evitada, +5 por honestidade, -20 vezes o risco estimado de revisão para declarações infladas e o bônus de +8 por estratégia nova em descrição repetida. O risco começa em 25% e se ajusta ao histórico de revisões. O agente compara as opções com o histórico; isso incentiva declarações honestas e infladas quando cada uma tem melhor retorno, sem fixar a ação por rodada.
- O técnico recebe como sinal a discrepância entre uma alegação máxima (3×3) e um relato de problema isolado/não crítico. Alertas anteriores tornam a revisão mais valiosa; revisões limpas repetidas tornam mais razoável poupar esforço.
- Se uma classificação P1 reaparecer após declarações de prioridade menor, o simulador sinaliza esse retorno ao técnico antes da decisão. O alerta é calculado a partir do histórico de classificações submetidas e não obriga o técnico a revisar.
- Quando uma descrição repetida recebe níveis diferentes de uma ocorrência anterior, o simulador mostra as declarações anteriores e sinaliza a variação para o técnico analisar. A mudança pode refletir uma gravidade diferente, portanto não é tratada automaticamente como fraude.
- Essas regras simplificam a interação descrita no Trabalho 1; não são regras operacionais do GLPI.

Os níveis declarados não são associados a números fixos de rodada. O solicitante escolhe qualquer par urgência/impacto entre 1 e 3 e recebe o histórico das próprias declarações, incluindo ocorrências com a mesma descrição; o técnico recebe o alerta de variação correspondente. O modelo pode escolher valores diferentes para o mesmo tipo de chamado, como 3/3, 2/3 e 1/1, mas essa sequência não é imposta. O transcript registra os valores, as decisões reais e os alertas calculados pelo simulador.

Se a chave estiver ausente, a chamada falhar ou a saída não obedecer ao formato, a execução para com erro explícito e imprime o histórico parcial. Nenhuma ação substituta é inventada.

## Arquitetura e limitações

- `src/adversarial_agents/agents.py`: cria os dois agentes Agno com Gemini e exige saída estruturada Pydantic.
- `src/adversarial_agents/simulation.py`: mantém histórico e estado, aplica regras, prepara observações por papel e produz o transcript.
- `src/adversarial_agents/models.py`: tipos de ações, cenário e validação adicional de respostas.
- `tests/`: verificações offline do simulador e dos limites de informação entre papéis.

O protótipo faz até dezesseis chamadas ao Gemini no cenário padrão (duas por rodada) ou duas no modo manual. A disponibilidade e o custo dependem da conta/provedor. Não persiste histórico entre execuções, não altera dados do GLPI e não mede tempos reais de atendimento. As justificativas são explicações curtas fornecidas pelo modelo, não logs de raciocínio interno.

## Solução de problemas

- `No module named adversarial_agents`: confirme que o terminal está na pasta extraída e reinstale com `& ".\.venv\Scripts\python.exe" -m pip install -e .`.
- `defina GOOGLE_API_KEY`: configure a chave na mesma janela do PowerShell e inicie novamente.
- Erro `429` ou cota excedida: aguarde o tempo indicado em `retryDelay` e confira os limites e o faturamento do projeto no Google AI Studio.
- O programa parece parado: acompanhe as mensagens “Aguardando decisão do agente” e “Pausa de cota”. O cenário padrão faz até 16 chamadas e pode levar alguns minutos.
