# Relacionamento

Depois de criar a tabela `Metas AV%`:

1. Vá em **Modelo** (ícone do diagrama, lado esquerdo).
2. Arraste **`Metas AV%`[AGRUPAMENTO]** sobre **`AGRUPAMENTO`[AGRUPAMENTO]**.
3. Confirme:
   - Cardinalidade: **Muitos para um (*:1)** (Metas → AGRUPAMENTO)
   - Direção do filtro cruzado: **Único** (de AGRUPAMENTO para Metas)
   - **Ativar este relacionamento**: marcado.

Isso garante que ao filtrar AGRUPAMENTO em qualquer visual, a meta correspondente seja trazida.
