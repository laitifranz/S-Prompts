import torch

def validate_state_dicts(model_state_dict_1, model_state_dict_2):
    if len(model_state_dict_1) != len(model_state_dict_2):
        print(
            f"Length mismatch: {len(model_state_dict_1)}, {len(model_state_dict_2)}"
        )
        return False

    # Replicate modules have "module" attached to their keys, so strip these off when comparing to local model.
    if next(iter(model_state_dict_1.keys())).startswith("module"):
        model_state_dict_1 = {
            k[len("module") + 1 :]: v for k, v in model_state_dict_1.items()
        }

    if next(iter(model_state_dict_2.keys())).startswith("module"):
        model_state_dict_2 = {
            k[len("module") + 1 :]: v for k, v in model_state_dict_2.items()
        }

    for ((k_1, v_1), (k_2, v_2)) in zip(
        model_state_dict_1.items(), model_state_dict_2.items()
    ):
        if k_1 != k_2:
            print(f"Key mismatch: {k_1} vs {k_2}")
        # # convert both to the same CUDA device
        # if str(v_1.device) != "cuda:0":
        #     v_1 = v_1.to("cuda:0" if torch.cuda.is_available() else "cpu")
        # if str(v_2.device) != "cuda:0":
        #     v_2 = v_2.to("cuda:0" if torch.cuda.is_available() else "cpu")

        if not torch.allclose(v_1, v_2):
            print(f"Tensor mismatch: {v_1} vs {v_2}")
            # return False
    print(f'N params 1: {sum(p.numel() for p in model_state_dict_1.values())}')
    print(f'N params 2: {sum(p.numel() for p in model_state_dict_2.values())}')


model_1 = torch.load('logs/logging/reproduce_1993_sprompts_slip_cddb_2_2_2023-10-31-15:48:56/task_0.tar')
model_2 = torch.load('logs/logging/reproduce_1993_sprompts_slip_cddb_2_2_2023-10-31-15:48:56/task_4.tar')

validate_state_dicts(model_1['model_state_dict'], model_2['model_state_dict'])

# [print(k_1 + '\n') for (k_1, v_1) in pretrained.state_dict().items()]
# print('##')
# [print(k_1 + '\n') for (k_1, v_1) in mymodel['model_state_dict'].items()]