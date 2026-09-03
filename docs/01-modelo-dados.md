# Modelo de Dados — extraído de `Modelo - Motores Governança e Acesso.drawio.html`

> Fonte da verdade do modelo. Convenção observada no diagrama: **snake_case** com
> prefixos semânticos (`id_`, `nome_`, `desc_`, `cod_`, `bol_`, `tipo_`, `datahora_`)
> e sufixo de assunto `_aisn` (Arquitetura da Informação). Todas as entidades
> carregam colunas de versionamento SCD2: `datahora_inicio_validade`,
> `datahora_fim_validade`, `bol_atual`, `bol_excluido`.

## Schema `governanca` (catálogo — mantido pelo Motor, consumido pelo App)

16 tabelas extraídas do diagrama:

### Catálogo / taxonomia
- **dominio_informacao** (PK `id_dominio_informacao`): nome_dominio, desc_dominio, +SCD2
- **subdominio_informacao** (PK `id_subdominio_informacao`, `id_dominio_informacao`):
  nome_subdominio, desc_subdominio → FK domínio
- **iniciativa_aisn** (PK `id_iniciativa_aisn`, `id_subdominio_informacao`):
  nome_iniciativa, desc_iniciativa, cod_status_iniciativa → FK subdomínio
- **camada_aisn** (PK `id_camada_aisn`): nome_camada, desc_camada  *(Bronze/Silver/Gold)*
- **ambiente_aisn** (PK `id_ambiente_aisn`): nome_ambiente, desc_ambiente
- **iniciativa_camada_ambiente** (PK composta: `id_iniciativa_camada_ambiente`,
  `id_iniciativa_aisn`, `id_camada_aisn`, `id_ambiente_aisn`): bol_elegivel_acesso.
  **É a unidade funcional de gestão de acesso (RN-001).**
- **tabela_aisn** (PK `id_tabela_aisn`, `id_iniciativa_camada_ambiente`):
  nome_catalogo, nome_schema, nome_tabela, desc_tabela, cod_status_tabela,
  bol_elegivel_acesso → FK iniciativa_camada_ambiente

### Owners (proprietários) — associações
- **dominio_proprietario** (PK `id_usuario_aisn`,`id_dominio_informacao`): cod_tipo_proprietario, bol_principal
- **subdominio_proprietario** (PK `id_usuario_aisn`,`id_subdominio_informacao`): idem
- **iniciativa_proprietario** (PK `id_usuario_aisn`,`id_iniciativa_aisn`): idem  ← **owner que aprova (RN-006)**
- **ativo_proprietario** (PK `id_usuario_aisn`,`id_ativo_aisn`): idem

### Usuários / hierarquia / grupos
- **usuario_aisn** (PK `id_usuario_aisn`): nome_usuario, nome_completo, desc_nome,
  desc_email, desc_sobrenome, cod_conta_databricks, bol_ativo, +SCD2
- **hierarquia_usuario** (PK `id_usuario_aisn`,`id_gestor_aisn`): mapeia usuário → gestor
  imediato (RN-013, RN-033). Self-FK em usuario_aisn.
- **grupo_acesso** (PK `id_grupo_acesso`): id_externo_grupo, cod_conta_databricks,
  nome_grupo, tipo_grupo *(grupo exploratório)*
- **grupo_acesso_membro** (PK `id_grupo_acesso`, ...): tipo_entidade, id_entidade,
  nome_entidade → FK grupo_acesso *(membros do grupo)*
- **ativo_aisn** (PK `id_grupo_acesso`,`id_ativo_aisn`): cod_tipo_ativo, nome_ativo,
  desc_ativo, bol_elegivel_acesso → FK grupo_acesso

## Relacionamentos (FKs no diagrama)
```
dominio_informacao 1─* subdominio_informacao 1─* iniciativa_aisn
iniciativa_aisn 1─* iniciativa_camada_ambiente *─1 camada_aisn
iniciativa_camada_ambiente *─1 ambiente_aisn
iniciativa_camada_ambiente 1─* tabela_aisn
usuario_aisn 1─* hierarquia_usuario (usuario, gestor)  [self-ref]
usuario_aisn 1─* {dominio|subdominio|iniciativa|ativo}_proprietario
grupo_acesso 1─* {grupo_acesso_membro, ativo_aisn}
ativo_aisn 1─* ativo_proprietario
```

## LACUNA IMPORTANTE — schema `gestao_acesso` NÃO está no diagrama
O `.drawio` entrega **apenas o catálogo de governança** (responsabilidade do Motor).
As entidades operacionais do **ciclo de vida do App** — solicitação, autorização
hierárquica, aprovação do owner, acesso concedido, revogação, execução técnica — que
os requisitos (RF-011 a RF-092) exigem, **precisam ser projetadas** por nós, seguindo
o mesmo estilo do modelo. Proposta em `docs/02-modelo-gestao-acesso.md` (a criar após
validação). Ver `docs/DECISIONS.md` D-002.
