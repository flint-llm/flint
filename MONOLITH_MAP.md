# Monolith Map — `flint/_salvage/monolith.py`

**File:** `flint/_salvage/monolith.py`
**Line count:** 4,777
**Surveyed:** 2026-04-22

---

## Concern buckets

| Bucket | Description |
|---|---|
| MODELS | Vocabulary types, tag normalisation, path helpers |
| TEMPLATES | Jinja2 rendering, template file management |
| K8S_APPLY | kubectl apply/delete/scale/rollout; Python k8s client reads |
| BUILD | Image pull/push (no Docker build — excluded per architecture doc) |
| LOGS | Pod log retrieval |
| ROUTING | Traffic split rendering + apply |
| CLUSTER | Cluster introspection: nodes, volumes, endpoints, namespace |
| UNCLEAR | Ambiguous or cross-cutting |
| DEAD | Training, SageMaker, streaming, Docker build, conda, tar/upload, Flask HTTP layer |

---

## Cross-cutting concerns

1. **Path normalisation** (`expandvars → expanduser → abspath → normpath`) — repeated 30+ times. Extracted into individual helpers or replaced by `pathlib.Path.resolve()` in the new modules.
2. **`_http_mode` dual-return pattern** — every public function returns either `jsonify(dict)` or the raw dict depending on a global flag. Entirely removed in Flint; modules return typed values and the CLI formats output.
3. **`_warnings.catch_warnings(simplefilter("ignore"))` wrapper** — wraps every kubernetes client call. Preserved in ported code.
4. **Error handling** — monolith uses `except: pass` or returns dicts with `"status": "incomplete"`. Flint raises typed exceptions from `errors.py`.
5. **`print()` as logger** — pervasive. Replaced with `logging.getLogger(__name__)` in all ported modules.

---

## Symbol inventory

### Global constants / registries (lines 60–150) — DEAD

| Name | Lines | Concern | Notes |
|---|---|---|---|
| `_kube_deploy_registry` | 61–84 | DEAD | Deprecated Dataspine service registry |
| `_kube_svc_registry` | 87–109 | DEAD | Deprecated |
| `_Dockerfile_template_registry` | 111–114 | DEAD | Docker build (excluded) |
| `_kube_router_*_template_registry` (×5) | 116–129 | DEAD | Dataspine-specific Istio templates |
| `_kube_stream_*_template_registry` (×4) | 126–129 | DEAD | Streaming feature |
| `_train_kube_template_registry` | 131–134 | DEAD | Training feature |
| `_default_*` constants | 136–150 | CLUSTER/MODELS | Default namespace, registry URLs; replaced by Flint defaults in models.py |

### Functions

| Name | Lines | Concern | Description |
|---|---|---|---|
| `_guild` | 158–162 | DEAD | Calls `guild` CLI tool |
| `_saved_model_cli` | 169–173 | DEAD | TF SavedModel CLI utility |
| `_convert_tf_export_format_to_savedmodel_format` | 176–215 | DEAD | TF export → SavedModel; uses undefined `tf`/`session` |
| `help` | 252–260 | DEAD | Flask route listing functions |
| `version` | 264–282 | DEAD | Flask route returning version dict |
| `_templates_path` | 296–301 | TEMPLATES | Returns default templates path |
| `_get_default_model_runtime` | 304–319 | DEAD | Maps old model_type to runtime; Flint uses vLLM/Ollama/TGI |
| `_validate_and_prep_model_tag` | 324–329 | MODELS | Normalize model tag → lowercase str → `normalize_model_name` |
| `_validate_and_prep_model_split_tag_and_weight_dict` | 332–340 | ROUTING | Validate weights sum to 100 → `validate_traffic_weights` |
| `clusterapi` | 345–378 | CLUSTER | Flask route: get model endpoint |
| `clusterapi_all` | 382–404 | CLUSTER | Flask route: get all endpoints |
| `_get_sage_endpoint_url` | 407–411 | DEAD | SageMaker endpoint URL |
| `_jupyter_kube_start` | 414–415 | DEAD | Empty stub |
| `_dashboard_kube_start` | 418–419 | DEAD | Empty stub |
| `deploy_getcluster` | 423–434 | DEAD | kubectl port-forward predict |
| `_service_connect` | 436–479 | DEAD | kubectl port-forward |
| `_environment_resources` | 482–513 | CLUSTER | kubectl top pod; not ported in S1 |
| `_service_resources` | 497–513 | CLUSTER | kubectl top pod for a service |
| `_create_predict_server_Dockerfile` | 516–555 | DEAD | Docker build — excluded by architecture |
| `_predict_server_describe` | 558–559 | DEAD | Empty stub |
| `_is_base64_encoded` | 562–574 | MODELS | Detect base64 encoding → `is_base64_encoded` |
| `_decode_base64` | 577–578 | MODELS | Decode base64 → `decode_base64` |
| `switch_condaenv` | 583–596 | DEAD | Conda env switch |
| `deploy_serverinit` | 600–677 | TEMPLATES | Render model scaffold templates to disk |
| `buildmodel_old` | 692–837 | DEAD | Old Docker build flow |
| `_set_build_context_path` | 839–845 | DEAD | Path normalisation for Docker build |
| `_set_dataspine_templates_path` | 848–856 | TEMPLATES | Normalise templates path → `resolve_templates_path` |
| `_set_model_path` | 859–870 | MODELS | Normalise model path |
| `_upload_dockerfile_to_s3` | 873–881 | DEAD | S3 upload |
| `buildmodel` | 885–978 | DEAD | Flask route: Docker build + S3 upload |
| `_create_predict_kube_Kubernetes_yaml` | 981–1104 | TEMPLATES | Render predict k8s YAML (deploy, svc, ingress, autoscale) → `render_deployment_templates` |
| `_create_stream_kube_Kubernetes_yaml` | 1107–1191 | DEAD | Streaming feature |
| `deploy_servershell` | 1194–1208 | DEAD | docker exec bash |
| `modelpush` | 1214–1252 | BUILD | docker push → `push_image` |
| `modelpull` | 1255–1275 | BUILD | docker pull → `pull_image` |
| `deploy_serverstart` | 1278–1328 | DEAD | docker run predict server |
| `deploy_serverstop` | 1331–1347 | DEAD | docker rm |
| `deploy_serverlogs` | 1350–1366 | DEAD | docker logs predict |
| `_service_rollout` | 1369–1409 | K8S_APPLY | kubectl set image + rollout → `rollout_image` |
| `_service_history` | 1412–1443 | K8S_APPLY | kubectl rollout history; not ported in S1 |
| `_service_rollback` | 1446–1489 | K8S_APPLY | kubectl rollout undo; not ported in S1 |
| `_filter_tar` | 1492–1498 | DEAD | tar filter |
| `buildmodel_tar` | 1501–1511 | DEAD | tar model |
| `_tar` | 1514–1542 | DEAD | create tar.gz |
| `buildmodel_untar` | 1545–1559 | DEAD | untar |
| `_untar` | 1562–1591 | DEAD | untar |
| `_allowed_file` | 1598–1602 | DEAD | file ext check for upload |
| `upload_tar` | 1605–1634 | DEAD | tar + upload |
| `uploadserver_tar` | 1657–1791 | DEAD | Flask route: file upload handler |
| `deploy_clusterstart` | 1797–1890 | K8S_APPLY | Main deploy flow: render YAML + apply → structure informs S3 |
| `_optimize_predict` | 2308–2325 | DEAD | Empty stub |
| `_optimize_train` | 2327–2344 | DEAD | Empty stub |
| `modeltest_http` | 2347–2364 | DEAD | HTTP predict test |
| `deploy_modeltest` | 2367–2414 | DEAD | Predict test via k8s endpoint |
| `deploy_modeltest_http` | 2417–2434 | DEAD | HTTP predict test |
| `_predict_http_test` | 2437–2488 | DEAD | Sends HTTP request to model endpoint |
| `_cluster_status` | 2644–2728 | CLUSTER | Full cluster status dump → `get_cluster_status` |
| `_get_pod_by_service_name` | 2731–2749 | K8S_APPLY | Find pod by name → `get_pod` |
| `_get_svc_by_service_name` | 2752–2771 | K8S_APPLY | Find service by name → `get_service` |
| `_get_all_available_services` | 2774–2779 | DEAD | Lists deprecated registry keys |
| `_get_all_nodes` | 2782–2793 | CLUSTER | List cluster nodes → `list_nodes` |
| `deploy_clustershell` | 2796–2815 | DEAD | kubectl exec bash |
| `_service_shell` | 2818–2847 | DEAD | kubectl exec bash |
| `deploy_clusterlogs` | 2851–2869 | LOGS | Get k8s pod logs → `get_deployment_logs` |
| `_service_logs` | 2872–2908 | LOGS | Tail k8s pod logs → `stream_pod_logs` |
| `_service_describe` | 2911–2933 | CLUSTER | kubectl describe pod |
| `deploy_clusterscale` | 2936–2965 | K8S_APPLY | Scale deployment → `scale_deployment` |
| `autoscale_cluster` | 2970–3020 | K8S_APPLY | kubectl autoscale; structure only in S1 |
| `deploy_sparkscale` | 3023–3038 | DEAD | Spark-specific |
| `_service_scale` | 3041–3076 | K8S_APPLY | kubectl scale deploy → `scale_deployment` |
| `_environment_volumes` | 3079–3109 | CLUSTER | List PVs and PVCs; not ported in S1 |
| `_get_deploy_yamls` | 3112–3123 | DEAD | Deprecated registry lookup |
| `_get_svc_yamls` | 3126–3137 | DEAD | Deprecated registry lookup |
| `_kube_apply` | 3140–3150 | K8S_APPLY | kubectl apply → `kube_apply` |
| `_kube_create` | 3152–3161 | K8S_APPLY | kubectl create; not ported (use apply in S3) |
| `_kube_delete` | 3164–3173 | K8S_APPLY | kubectl delete → `kube_delete` |
| `_kube` | 3176–3181 | K8S_APPLY | Run kubectl command → `_run_kubectl` |
| `deploy_clusterinfo` | 3184–3210 | CLUSTER | Print endpoints and routes |
| `describeroutes` | 3213–3241 | ROUTING | kubectl get ingress + routerules → `describe_routes` |
| `_get_model_kube_endpoint` | 3245–3284 | CLUSTER | Get ingress endpoint URL → `get_model_endpoint` |
| `_get_istio_ingress_nodeport` | 3287–3290 | CLUSTER | Get Istio ingress nodeport → `_get_ingress_nodeport` |
| `_get_istio_ingress_ip` | 3293–3296 | CLUSTER | Get Istio ingress IP → `_get_ingress_ip` |
| `_get_all_model_endpoints` | 3300–3340 | CLUSTER | Get all ingress endpoints → `get_all_endpoints` |
| `_get_cluster_service` | 3343–3379 | CLUSTER | Get service endpoint → `get_service_endpoint` |
| `_istio_apply` | 3382–3406 | K8S_APPLY | istioctl kube-inject + apply; TODO(S5) replace with Gateway API |
| `routetraffic` | 3419–3528 | ROUTING | Render routerules YAML + apply → `apply_traffic_split` |
| `_service_start` | 3531–3578 | K8S_APPLY | Start service from deprecated registry; not ported |
| `deploy_clusterstop` | 3585–3609 | K8S_APPLY | Delete deployment → `delete_deployment` |
| `_service_stop` | 3612–3643 | K8S_APPLY | kubectl delete deploy → `delete_deployment` |
| `trainer_serverpull` | 3646–3666 | BUILD | docker pull train image → `pull_image` |
| `trainer_serverpush` | 3669–3689 | BUILD | docker push train image → `push_image` |
| `trainer_serverlogs` | 3692–3707 | DEAD | docker logs train |
| `trainer_servershell` | 3710–3724 | DEAD | docker exec train |
| `_create_train_server_Dockerfile` | 3727–3784 | DEAD | Render train Dockerfile |
| `trainer_serverbuild` | 3787–3907 | DEAD | docker build train |
| `trainer_serverstart` | 3910–3971 | DEAD | docker run train |
| `trainer_serverstop` | 3973–3989 | DEAD | docker rm train |
| `_create_train_kube_yaml` | 3992–4061 | DEAD | Render TF training k8s YAML |
| `trainer_getcluster` | 4064–4084 | DEAD | port-forward train |
| `trainer_clusterinfo` | 4087–4102 | DEAD | describe train pod |
| `trainer_clustershell` | 4105–4121 | DEAD | kubectl exec train |
| `trainer_clusterstart` | 4124–4221 | DEAD | Deploy TF training job |
| `trainer_clusterstop` | 4227–4243 | DEAD | Stop training deployment |
| `trainer_clusterlogs` | 4248–4274 | DEAD | Log training pod |
| `trainer_clusterscale` | 4282–4302 | DEAD | Scale training deployment |
| `sage_serverstart` | 4305–4418 | DEAD | SageMaker deploy |
| `sage_routetraffic` | 4428–4555 | DEAD | SageMaker traffic routing |
| `_get_sage_endpoint_config` | 4558–4593 | DEAD | SageMaker endpoint config |
| `_get_sage_endpoint` | 4596–4634 | DEAD | SageMaker endpoint |
| `_image_to_json` | 4638–4656 | DEAD | Image conversion stub (undefined `Image`) |
| `_image_to_numpy` | 4659–4671 | DEAD | Image to numpy (undefined `np`, `skimage`) |
| `_image_to_json2` | 4676–4683 | DEAD | Image to JSON |
| `_stream` | 4692–4730 | DEAD | Flask SSE streaming endpoint |
| `_stream_page` | 4733–4735 | DEAD | Flask redirect |
| `_main` | 4742–4743 | DEAD | Flask app.run entry point |

---

## Concern bucket counts

| Bucket | Count |
|---|---|
| DEAD | 63 |
| K8S_APPLY | 14 |
| CLUSTER | 12 |
| TEMPLATES | 5 |
| MODELS | 5 |
| ROUTING | 3 |
| BUILD | 2 |
| LOGS | 2 |

---

## Judgment calls

1. **Templates**: The salvage templates (`yaml/*.template`) target Dataspine/Istio and are incompatible with Flint's stack (Gateway API + vLLM/Ollama/TGI). Decision: port the rendering engine (Jinja2 pattern from `_create_predict_kube_Kubernetes_yaml`) into `templates.py`; create new Flint-native templates under `flint/templates/vllm/`. Old salvage templates are reference only.

2. **subprocess vs Python k8s client for writes**: Monolith uses subprocess `kubectl` for write operations and the Python k8s client for reads. S3 will migrate writes to server-side apply via Python client. In S1, write operations preserve the subprocess pattern with `TODO(S3)` markers.

3. **build.py scope**: Architecture doc explicitly excludes Docker image builds from v0.1. Only `push_image`, `pull_image`, and `resolve_runtime_image` are ported. All `buildmodel*`, `_create_*_Dockerfile`, `trainer_server*` functions are marked DEAD.

---

## Questions

None that require stopping. The three judgment calls above have clear decisions.
