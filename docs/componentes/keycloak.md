# Keycloak do painel TudoIA

O painel TudoIA faz login por OIDC (Authorization Code + PKCE) em um realm próprio do
Keycloak, chamado `tudoia`. O realm é provisionado por código: o script
`scripts/keycloak/provisionar.py` aplica o template `infra/keycloak/realm-tudoia.json`
e os identity providers em `infra/keycloak/idps/`. Rodar de novo não duplica nada e só
altera o que divergir do template.

O Keycloak vem no `runtime/docker-compose.yml` (serviços `keycloak` e `keycloak-db`, perfil `keycloak` em
`COMPOSE_PROFILES`, porta 8180 só em `127.0.0.1`, modo `start` com HTTP, tema de login do TudoIA montado). A senha do
admin do realm `master` (`TUDOIA_KEYCLOAK_ADMIN_PASSWORD`) e a do banco (`KEYCLOAK_DB_PASSWORD`) são geradas por
`tudoia segredos`. Quem prefere um Keycloak próprio tira `keycloak` de `COMPOSE_PROFILES` e o mantém em `localhost:8180`.

## O que o provisionamento cria

| Recurso | Detalhe |
|---|---|
| Realm `tudoia` | cadastro público desligado, login por e-mail, recuperação de senha ligada, brute force protegido, `sslRequired=external`, sem política de senha (desligada a pedido do dono, ambiente interno de desenvolvimento; ver seguranca.md), sessão SSO 8 h ociosa / 24 h máximo |
| Papéis de realm | `tudoia-admin`, `tudoia-operador`, `tudoia-leitor` |
| Grupos | `tudoia-admin`, `tudoia-operador`, `tudoia-leitor`, cada um mapeado ao papel de mesmo nome |
| Client scope `tudoia-groups` | mapper *Group Membership* → claim `groups` (só o nome, sem caminho) no ID token, access token, userinfo e introspection |
| Client `tudoia-painel` | confidencial; Authorization Code com PKCE `S256`; sem implicit, sem direct grant, sem service account; escopos padrão `profile`, `email`, `roles`, `tudoia-groups`; `access.token.lifespan = 28800` (8 h) |
| Client `tudoia-mcp` | confidencial, só `client_credentials` (conta de serviço no grupo `tudoia-operador`); mapper de audiência `tudoia-mcp`; token de 8 h (`28800`). Usado pelo Cérebro e pelo n8n (ver [cerebro.md](cerebro.md#token-do-cliente-tudoia-mcp)) |
| Client `tudoia-capturas` | confidencial, só `client_credentials` (conta no grupo `tudoia-leitor`); token de 300 s, com mapper de audiência `tudoia-painel` (o painel recusa Bearer sem `aud` = `tudoia-painel`). Capturas de tela do Studio |
| Redirect URIs | `http://127.0.0.1:<porta>/auth/callback` e `http://localhost:<porta>/auth/callback` (porta = `TUDOIA_PAINEL_PORTA`, padrão 3100) |
| Logout | `post.logout.redirect.uris` para as mesmas origens |
| Identity providers | um arquivo por IdP em `infra/keycloak/idps/` (não `.example.json`) |
| Segredo do client | gerado pelo Keycloak e gravado no `.env` do TudoIA; nunca fica no template |

Os papéis e grupos que existem no realm mas não estão no template não são removidos.
Já os mapeamentos de papel dos grupos gerenciados são sincronizados exatamente: papel
sobrando em `tudoia-leitor` é removido, porque isso seria escalonamento de privilégio.

## Pré-requisitos

- Keycloak no ar (`http://localhost:8180`). O realm `master` precisa ter um admin real.
- Credenciais de um admin do realm `master` (`TUDOIA_KEYCLOAK_ADMIN` e
  `TUDOIA_KEYCLOAK_ADMIN_PASSWORD`, ou digitadas no terminal quando solicitado).
- Python do venv do projeto (`D:\TudoIA\.venv`); o script usa só `httpx`, já dependência.

Atenção: `KC_BOOTSTRAP_ADMIN_*` do compose só cria o admin na **primeira** inicialização
do banco. Se o `.env` do Keycloak mudou depois, o admin de lá pode não existir mais e o
login falha com HTTP 401 (`user_not_found` no log). Corrija o admin pelo console ou pelo
`kcadm.sh` dentro do container antes de provisionar.

## Como rodar

Na raiz `D:\TudoIA`:

```bash
# 1. Comparar o template com o Keycloak (somente leitura; sai com 1 se houver desvio)
D:/TudoIA/.venv/Scripts/python.exe -m scripts.keycloak.provisionar --verificar

# 2. Aplicar (idempotente; a segunda execução deve imprimir "igual")
D:/TudoIA/.venv/Scripts/python.exe -m scripts.keycloak.provisionar

# 3. Criar o primeiro administrador do painel (senha temporária exibida uma vez)
D:/TudoIA/.venv/Scripts/python.exe -m scripts.keycloak.provisionar --admin-inicial pessoa@dominio.com

# 4. Trocar o segredo do client tudoia-painel (e reenviar os segredos dos IdPs)
D:/TudoIA/.venv/Scripts/python.exe -m scripts.keycloak.provisionar --rotacionar-secret
```

Variáveis (ambiente tem prioridade sobre `D:\TudoIA\.env`):

| Variável | Padrão | Uso |
|---|---|---|
| `TUDOIA_KEYCLOAK_URL` | `http://localhost:8180` | URL base do Keycloak |
| `TUDOIA_KEYCLOAK_REALM` | `tudoia` | realm a provisionar |
| `TUDOIA_PAINEL_PORTA` | `3100` | porta dos redirect URIs |
| `TUDOIA_KEYCLOAK_ADMIN` | (pede no terminal) | admin do realm `master` |
| `TUDOIA_KEYCLOAK_ADMIN_PASSWORD` | (pede no terminal) | senha do admin |

Códigos de saída: `0` ok ou sem alterações, `1` desvio ou erro de validação,
`2` conexão ou autenticação. Mensagens de erro não mostram segredos nem tokens.

O `.env` recebe, só quando o valor muda:

- `TUDOIA_OIDC_ISSUER` = `http://localhost:8180/realms/tudoia`
- `TUDOIA_OIDC_CLIENT_ID` = `tudoia-painel`
- `TUDOIA_OIDC_CLIENT_SECRET`
- `TUDOIA_MCP_CLIENT_ID` = `tudoia-mcp` e `TUDOIA_MCP_CLIENT_SECRET`
- `TUDOIA_CAPTURAS_CLIENT_ID` e `TUDOIA_CAPTURAS_CLIENT_SECRET` (quando o template define o cliente de capturas)

Cada alteração do `.env` gera backup em `D:\TudoIA\dados\backups\env`.

### Validade do token do painel

O painel reconfirma a sessão no `userinfo` a cada 30 s com o `access_token` guardado no login. Por isso o token do
cliente `tudoia-painel` precisa durar o mesmo que a sessão (8 h). O template define `access.token.lifespan = 28800`.
Sem esse atributo valia o padrão do realm (300 s): o token vencia, o `userinfo` respondia 401 e o painel derrubava a
sessão em 5 min. O provisionador exige `access.token.lifespan` numérico só nos clientes de serviço (`tudoia-mcp`,
`tudoia-capturas`). No `tudoia-painel` não há essa checagem: se o atributo sair do template, a sessão volta a cair em
5 min.

O valor só chega ao Keycloak em execução quando o provisionamento roda:

```bash
D:/TudoIA/.venv/Scripts/python.exe -m scripts.keycloak.provisionar --verificar   # mostra o desvio
D:/TudoIA/.venv/Scripts/python.exe -m scripts.keycloak.provisionar               # aplica
```

Depois disso, saia e entre de novo no painel: a sessão aberta ainda tem o token antigo, de 5 min.

## Adicionar um usuário

- Primeiro administrador: `--admin-inicial EMAIL`. O usuário entra no grupo
  `tudoia-admin`, recebe senha temporária aleatória (mostrada uma vez) e é obrigado a
  trocá-la no primeiro login. Se o usuário já existir, nada é alterado.
- Demais usuários: no console (`http://localhost:8180/admin`, realm `tudoia`), crie o
  usuário, marque o e-mail como verificado se for o caso, e coloque-o em um dos grupos
  `tudoia-admin`, `tudoia-operador` ou `tudoia-leitor`. O papel vem do grupo.

## Adicionar um identity provider (Entra ID)

1. Registre um aplicativo no Entra ID com a URI de redirecionamento do broker:
   `http://localhost:8180/realms/tudoia/broker/entra-id/endpoint`. Gere um segredo de
   cliente e anote o ID do locatário (tenant), o ID do aplicativo e o valor do segredo.
2. Para o claim `groups`, configure o aplicativo para emitir os grupos. O Entra envia
   **IDs de objeto** (GUIDs) dos grupos. Anote o ID de cada grupo que deve virar
   `tudoia-admin`, `tudoia-operador` ou `tudoia-leitor`. Para grupos grandes, o Entra
   pode mandar "overage"; nesse caso use atribuição de grupos por aplicativo.
3. Copie o exemplo para um nome real (sem `.example`):

   ```bash
   cp infra/keycloak/idps/entra-id.example.json infra/keycloak/idps/entra-id.json
   ```

   Os nomes dos arquivos `*.example.json` não são aplicados; qualquer outro `*.json` é.
4. Coloque as variáveis no `D:\TudoIA\.env` (ou no ambiente):

   ```
   TUDOIA_IDP_ENTRA_TENANT_ID=...
   TUDOIA_IDP_ENTRA_CLIENT_ID=...
   TUDOIA_IDP_ENTRA_CLIENT_SECRET=...
   TUDOIA_IDP_ENTRA_GRUPO_ADMIN_OID=...
   TUDOIA_IDP_ENTRA_GRUPO_OPERADOR_OID=...
   TUDOIA_IDP_ENTRA_GRUPO_LEITOR_OID=...
   ```

5. Rode `--verificar` e depois a aplicação. Se faltar qualquer variável, o script para
   com erro antes de tocar no Keycloak; nunca cria um IdP com segredo vazio.
6. Teste o login pelo botão do Entra no console do Keycloak (Identity providers > entra-id)
   e confira no usuário de teste se os grupos chegaram. O mapper usa o campo `group` com
   o caminho do grupo (`/tudoia-admin`). Confirme isso na primeira aplicação, porque a
   forma exata do campo depende da versão do Keycloak.

Para outro provedor OIDC, copie `oidc-generico.example.json` do mesmo jeito, troque
`TUDOIA_IDP_OIDC_*` pelos valores do provedor e ajuste o mapper de grupos.

Para um provedor que não é OIDC (SAML, por exemplo), crie o arquivo JSON com o
`providerId` correspondente e valide os campos com a documentação do Keycloak. O script
aplica o que estiver no JSON, mas não conhece as regras de cada tipo.

## Microsoft Entra ID (via brokering)

Resumo do fluxo: o Entra autentica o usuário, o Keycloak recebe o retorno pelo broker e o painel só fala com o
Keycloak. Os passos abaixo cobrem o que o repositório permite verificar. O que depende do seu tenant está na última
seção.

### O que fazer no Entra

1. Registre um aplicativo (App registration) no seu tenant.
2. Em **Redirect URI** (tipo Web), use o endpoint do broker do Keycloak:
   `https://<keycloak>/realms/tudoia/broker/<alias>/endpoint`. O alias do exemplo do repositório é `entra-id`, e a
   URI fica `https://<keycloak>/realms/tudoia/broker/entra-id/endpoint`. Na instância local do repositório, o endereço
   é `http://localhost:8180/realms/tudoia/broker/entra-id/endpoint`.
3. Crie um **client secret** e guarde o valor. O Entra mostra o valor uma vez.
4. Em **API permissions** (Microsoft Graph, delegadas), mantenha `openid`, `profile` e `email`. São os escopos do
   `defaultScope` do exemplo.
5. Opcional: configure o claim `groups` no token, para o Keycloak receber os grupos. Ver a última seção.

### Onde os valores entram no Keycloak

1. Copie o exemplo para um arquivo sem `.example`:

   ```bash
   cp infra/keycloak/idps/entra-id.example.json infra/keycloak/idps/entra-id.json
   ```

   Só arquivos `*.json` sem `.example` são aplicados. O arquivo `entra-id.json` **não** está no `.gitignore`. Por isso
   ele deve manter os placeholders `${TUDOIA_IDP_...}`. O segredo nunca vai para o JSON: o provisionador troca os
   placeholders na memória, a partir do `.env`.

2. No `D:\TudoIA\.env` (ou no ambiente), preencha as variáveis que o exemplo referencia:

   ```
   TUDOIA_IDP_ENTRA_TENANT_ID=...
   TUDOIA_IDP_ENTRA_CLIENT_ID=...
   TUDOIA_IDP_ENTRA_CLIENT_SECRET=...
   TUDOIA_IDP_ENTRA_GRUPO_ADMIN_OID=...
   TUDOIA_IDP_ENTRA_GRUPO_OPERADOR_OID=...
   TUDOIA_IDP_ENTRA_GRUPO_LEITOR_OID=...
   ```

   O exemplo exige as seis. Se qualquer uma estiver vazia, o provisionador para com `variável(is) ausente(s)` antes de
   chamar o Keycloak.

3. Rode o provisionador de novo:

   ```bash
   python -m scripts.keycloak.provisionar --verificar   # mostra desvios, sem aplicar
   python -m scripts.keycloak.provisionar               # aplica
   ```

   No Windows, o equivalente é `.\scripts\tudoia.ps1 keycloak`. A segunda execução deve dizer que está igual.

### O que o painel precisa

Nada novo. O painel conhece apenas o issuer do Keycloak (`TUDOIA_OIDC_ISSUER`). O Entra é um identity provider
configurado dentro do Keycloak, e o painel não o consulta diretamente.

### Não verificado neste repositório (a confirmar, depende do seu tenant)

- **ID do tenant:** o repositório não contém esse valor. Ele vem do seu Entra. A confirmar.
- **Claim `groups`:** não sei se o seu aplicativo emite o claim, porque isso depende da configuração de token do
  registro. Para grupos demais, o Entra envia "overage" em vez da lista; a alternativa é atribuir os grupos ao
  aplicativo. A confirmar.
- **Mapper de grupos:** o exemplo usa `oidc-advanced-group-idp-mapper`, com `claims` igual a
  `[{"key":"groups","value":"<ID de objeto do grupo>"}]` e `group` igual a `/tudoia-admin` (ou operador/leitor). A forma
  do campo depende da versão do Keycloak, e este mapper nunca foi aplicado nesta instalação. A confirmar.
- **Login de ponta a ponta com o Entra:** não executado. Teste pelo botão do Entra no console do Keycloak e confira
  os grupos no usuário de teste.

## Rotacionar o segredo

```bash
D:/TudoIA/.venv/Scripts/python.exe -m scripts.keycloak.provisionar --rotacionar-secret
```

Isso gera um novo segredo do client `tudoia-painel`, grava no `.env` e reenvia os
segredos dos IdPs a partir das variáveis. Depois reinicie o painel para ele usar o novo
valor. O segredo antigo deixa de funcionar imediatamente.

Os segredos dos IdPs (`TUDOIA_IDP_*_CLIENT_SECRET`) não são comparados com o Keycloak,
porque ele devolve o valor mascarado. Por isso trocar uma dessas variáveis só tem efeito
com `--rotacionar-secret`, ou quando outro campo daquele IdP também mudar.

## Solução de problemas

- **`credenciais de administrador recusadas` (exit 2):** o usuário não existe no
  `master` ou a senha está errada. Veja o aviso sobre `KC_BOOTSTRAP_ADMIN_*` na seção
  de pré-requisitos.
- **`não foi possível conectar` (exit 2):** o Keycloak não está no ar, ou
  `TUDOIA_KEYCLOAK_URL` aponta para outra porta. Teste:
  `curl http://localhost:8180/realms/master/.well-known/openid-configuration`.
- **`variável(is) ausente(s): ...` (exit 1):** falta uma variável de um IdP. Veja o
  passo 4 de Adicionar um identity provider.
- **Desvio do `--verificar` (exit 1):** o registro mostra o campo divergente. Rode a
  aplicação para corrigir. Se a divergência for em um papel extra num grupo gerenciado,
  a aplicação remove o papel.
- **Issuer diferente entre navegador e backend (`invalid issuer`, `iss` não confere):**
  o issuer é fixo em `http://localhost:8180/realms/tudoia`. O painel roda no host, então
  o navegador e o backend alcançam o mesmo endereço. Se o painel passar a rodar em
  container, o backend não alcança `localhost` (é o próprio container). Nesse caso use
  `host.docker.internal` no backend e defina `KC_HOSTNAME` e
  `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` na stack do Keycloak, como já é feito para o
  outros serviços e o LiteLLM (veja o README da sua stack do Keycloak).
- **`Invalid redirect_uri` no login:** a porta do painel (`TUDOIA_PAINEL_PORTA`) não é a
  mesma que o redirect URI registrado. Ajuste a variável e rode a aplicação de novo.
- **Login funciona, mas os grupos não aparecem no token:** confira se o client scope
  `tudoia-groups` está em `defaultClientScopes` do client e se o mapper `groups` existe.
  O `--verificar` aponta os dois casos.

## Segurança

- O template não tem segredos. Um teste falha se alguma chave com `secret` aparecer nele.
- O client exige PKCE `S256`. Não há direct grant (senha no backend) nem implicit flow.
- Cadastro público é desligado e o brute force é protegido.
- A conta `master` é só para administrar o Keycloak. O painel usa apenas o realm
  `tudoia`.
- Os papéis vêm dos grupos. Só o script (ou um admin do realm) deve mudar a composição
  dos grupos `tudoia-*`.
- IdPs externos com `trustEmail: true` (como o Entra) confiam no e-mail informado pelo
  provedor. Só ligue essa opção quando o provedor for controlado pela organização.
- Os segredos ficam só no `.env` (gitignored) e no Keycloak. O script não os imprime nem
  os coloca em URLs ou logs.

## Testes

```bash
D:/TudoIA/.venv/Scripts/python.exe -m pytest -q tests/keycloak
```

Os testes não usam a rede. O teste de integração contra o Keycloak vivo só roda com
`TUDOIA_KEYCLOAK_IT=1` (e as credenciais de admin no ambiente).

## Tema da tela de login

A tela de login usa o tema `tudoia`, com as cores e o logo do painel. Ele fica em `infra/keycloak/tema/tudoia/login/`
(`theme.properties`, CSS, logo e textos em pt-BR), e herda o tema padrão `keycloak.v2`.

Para o Keycloak enxergar o tema, a pasta precisa estar montada no container. Na instância local, no
`docker-compose.yml` do Keycloak, no serviço `keycloak`:

    volumes:
      - D:/TudoIA/infra/keycloak/tema/tudoia:/opt/keycloak/themes/tudoia:ro

Depois: `docker compose up -d` e `python -m scripts.keycloak.provisionar`. O realm (`loginTheme: tudoia`) e o idioma
(pt-BR) vêm do template. Em outra instalação, ajuste o caminho da montagem para onde o repositório estiver.
Para ver o tema novo, recarregue a tela de login com cache limpo (Ctrl+F5).

O tema usa Bricolage Grotesque e JetBrains Mono, servidas localmente (`resources/fonts`, licença OFL em `LICENCA.md`).
A órbita da esquerda tem duas versões: animada (`orbita.svg`) e estática (`orbita-estatica.svg`), escolhida
automaticamente para quem pede redução de movimento no sistema.
