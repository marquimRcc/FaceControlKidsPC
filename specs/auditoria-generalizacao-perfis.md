# Relatório de Auditoria: Generalização de Perfis e Instaladores (SDD)

**Data:** 2026-11-05  
**Escopo:** Avaliação de suposições de "3 perfis" legados vs. arquitetura 1+ perfis em código, scripts e instaladores.  
**Conclusão Geral:** Aprovado com ressalvas delimitadas (testes legados mantidos propositalmente para compatibilidade).

---

## 1. Mapeamento de Ocorrências de "3 Perfis"

| Arquivo | Trecho / Função | Tipo de Uso | Status / Parecer SDD |
|---|---|---|---|
| `facekids/child_quota_pilot.py` | `provision_three_children(store)` | Fixture legado de bancada | **Isolado:** Apenas consumido por unitários sintéticos legados. O runtime oficial usa `configured_child_profiles(store)`. |
| `tests/test_child_quota_pilot.py` | Testes com 3 crianças sintéticas | Testes de regressão | **Preservado:** Garante estabilidade retroativa de cálculo de quotas sem afetar produção. |
| `tests/test_children_pilot.py` | Testes de piloto com 3 crianças | Testes de regressão | **Preservado:** Cobertura de transição. |
| `tests/test_linux_auth.py` | Testes Regata OS | Testes Linux | **Isolado:** Não interfere no Windows. |

---

## 2. Auditoria dos Instaladores Windows

| Script | Verificação Realizada | Resultado |
|---|---|---|
| `Instalar-FaceUnlock.bat` | Wrapper com elevação UAC para o PowerShell nativo | **Conforme:** Apenas repassa a execução. |
| `scripts/Instalar-FaceKids-Nativo.ps1` | Instalação da DLL C++, serviço, agente interativo e configuração de quota | **Conforme:** Não contém slots fixos de 3 perfis. Trata a conta `Filhos` de forma genérica. |
| `scripts/Ativar-Desbloqueio-No-Boot.ps1` | Criação de tarefa agendada SYSTEM | **Conforme:** Totalmente desacoplado de IDs de perfis. |
| `scripts/Iniciar-Piloto-Filhos.ps1` | Menu de console para cadastro facial e quotas | **Conforme:** Já suporta `add-profile` dinâmico (1..N perfis). |

---

## 3. Resolução da Trava de Branch em `Iniciar-Teste-Adulto-Filhos.ps1`

- **Comportamento Observado:** O script valida se o branch ativo é estritamente `fix/facekids-ipc-security-hardening-20261024`.
- **Governança SDD:** Para não alterar scripts de homologação congelados, a execução presencial deve ser feita utilizando o comando canônico de laboratório, que clona/atualiza a branch correta em `%LOCALAPPDATA%\FaceKids\codigo-laboratorio-adulto`.
