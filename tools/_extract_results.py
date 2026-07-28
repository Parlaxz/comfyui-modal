import json, sys
data = json.load(open(sys.argv[1]))
for r in data['runs']:
    t = r['timing']
    ident = r['identity']
    print(f"Run {r['run_index']:2d} | req_id={r['request_id']} | container={ident['restored_instance_id'][:12]} | restore_count={ident['restore_count']} request_count={ident['request_count']}")
    print(f"  restore_total={t.get('restore_total_ms','?')} | snapshot_restore={t.get('snapshot_restore','?')} | clip_raw_encode={t.get('clip_raw_encode_ms','?')}")
    print(f"  unet_gpu_load={t.get('graph_gpu_load','?')} | gpu_restore={t.get('restore_gpu_state','?')} | cuda_init={t.get('cuda_init','?')}")
    print(f"  trigger_to_durable={t.get('trigger_to_durable_result_ms',t.get('trigger_to_result_local_ms','?'))} | wall={t.get('wall_ms','?')}")
    print(f"  sampling={t.get('sampling','?')} | output_encode={t.get('output_encode','?')} | load_models_gpu={t.get('load_models_gpu_duration_ms','?')}")
    print()
