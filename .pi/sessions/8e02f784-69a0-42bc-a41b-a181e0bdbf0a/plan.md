---
status: in_progress
updatedAt: 2026-04-03T14:01:32.337Z
---

# Mode HCL-only : Retirer la dépendance à Terraform CLI

## 1. Objective

Ajouter un mode `--no-terraform` / `--hcl-only` qui génère des diagrammes d'architecture uniquement à partir du parsing HCL des fichiers .tf, sans nécessiter terraform init/plan/graph.

## 2. Context

Le pipeline actuel dépend de 3 commandes terraform (init, plan, graph). L'exploration montre que :
- Le parser HCL existant extrait déjà toutes les ressources et attributs
- `add_relations()` détecte déjà les dépendances par scan des refs HCL
- Le gap principal = construction du graphdict initial + gestion count/for_each + modules distants

## 3. Tasks

1. Créer `modules/hcl_graph_builder.py` — construit graphdict depuis all_resource/all_data
2. Adapter le CLI et le pipeline — flag `--no-terraform`, routing, preflight
3. Gestion des modules distants sans terraform init
4. Tests et validation

## 4. Validation

- [ ] `terravision draw --source ./my-tf-project --no-terraform` génère un diagramme
- [ ] `terravision graphdata --source ./my-tf-project --no-terraform` génère le JSON
- [ ] Pas besoin de terraform installé en mode HCL-only
- [ ] Les diagrammes sont cohérents avec le mode terraform-backed
- [ ] Tests existants passent toujours
