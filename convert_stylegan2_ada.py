"""
Based on https://github.com/dvschultz/stylegan2-ada-pytorch
"""

import re
from argparse import ArgumentParser

import numpy as np
import torch


def convert_to_rgb(state_ros, state_nv, ros_name, nv_name):
    state_ros[f"{ros_name}.conv.weight"] = state_nv[f"{nv_name}.torgb.weight"].unsqueeze(0)
    state_ros[f"{ros_name}.bias"] = state_nv[f"{nv_name}.torgb.bias"].unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
    state_ros[f"{ros_name}.conv.modulation.weight"] = state_nv[f"{nv_name}.torgb.affine.weight"]
    state_ros[f"{ros_name}.conv.modulation.bias"] = state_nv[f"{nv_name}.torgb.affine.bias"]


def convert_conv(state_ros, state_nv, ros_name, nv_name):
    state_ros[f"{ros_name}.conv.weight"] = state_nv[f"{nv_name}.weight"].unsqueeze(0)
    state_ros[f"{ros_name}.activate.bias"] = state_nv[f"{nv_name}.bias"]
    state_ros[f"{ros_name}.conv.modulation.weight"] = state_nv[f"{nv_name}.affine.weight"]
    state_ros[f"{ros_name}.conv.modulation.bias"] = state_nv[f"{nv_name}.affine.bias"]
    state_ros[f"{ros_name}.noise.weight"] = state_nv[f"{nv_name}.noise_strength"].unsqueeze(0)


def convert_blur_kernel(state_ros, state_nv, level):
    """Not quite sure why there is a factor of 4 here"""
    # They are all the same
    state_ros[f"convs.{2 * level}.conv.blur.kernel"] = 4 * state_nv["synthesis.b4.resample_filter"]
    state_ros[f"to_rgbs.{level}.upsample.kernel"] = 4 * state_nv["synthesis.b4.resample_filter"]


def determine_config(state_nv):
    mapping_names = [name for name in state_nv.keys() if "mapping.fc" in name]
    sythesis_names = [name for name in state_nv.keys() if "synthesis.b" in name]

    n_mapping = max([int(re.findall("(\d+)", n)[0]) for n in mapping_names]) + 1
    resolution = max([int(re.findall("(\d+)", n)[0]) for n in sythesis_names])
    n_layers = np.log(resolution / 2) / np.log(2)

    return n_mapping, n_layers


def convert(network_pkl, output_file):
    try:
        import dnnlib
        import legacy
    except Exception:
        print("You have run this code from github.com/NVlabs/stylegan2-ada-pytorch folder")
        raise

    with dnnlib.util.open_url(network_pkl) as f:
        G_nvidia = legacy.load_network_pkl(f)["G_ema"]

    state_nv = G_nvidia.state_dict()
    n_mapping, n_layers = determine_config(state_nv)

    state_ros = {}

    for i in range(n_mapping):
        state_ros[f"style.{i + 1}.weight"] = state_nv[f"mapping.fc{i}.weight"]
        state_ros[f"style.{i + 1}.bias"] = state_nv[f"mapping.fc{i}.bias"]

    for i in range(int(n_layers)):
        if i > 0:
            for conv_level in range(2):
                convert_conv(state_ros, state_nv, f"convs.{2 * i - 2 + conv_level}",
                             f"synthesis.b{4 * (2 ** i)}.conv{conv_level}")
                state_ros[f"noises.noise_{2 * i - 1 + conv_level}"] = state_nv[
                    f"synthesis.b{4 * (2 ** i)}.conv{conv_level}.noise_const"].unsqueeze(0).unsqueeze(0)

            convert_to_rgb(state_ros, state_nv, f"to_rgbs.{i - 1}", f"synthesis.b{4 * (2 ** i)}")
            convert_blur_kernel(state_ros, state_nv, i - 1)

        else:
            state_ros[f"input.input"] = state_nv[f"synthesis.b{4 * (2 ** i)}.const"].unsqueeze(0)
            convert_conv(state_ros, state_nv, "conv1", f"synthesis.b{4 * (2 ** i)}.conv1")
            state_ros[f"noises.noise_{2 * i}"] = state_nv[f"synthesis.b{4 * (2 ** i)}.conv1.noise_const"].unsqueeze(
                0).unsqueeze(0)
            convert_to_rgb(state_ros, state_nv, "to_rgb1", f"synthesis.b{4 * (2 ** i)}")

    state_dict = {"g_ema": state_ros}
    torch.save(state_dict, output_file)


def main():
    parser = ArgumentParser()
    parser.add_argument("--pkl", type=str, required=True, help='Path to the stylegan ada pytorch pkl file')
    parser.add_argument("--out", type=str, default='model.pth', help='Path to a file where to save weights')
    parser.add_argument("--repo", type=str, default='stylegan2-ada-pytorch',
                        help='Path to the cloned repo github.com/NVlabs/stylegan2-ada-pytorch')
    args = parser.parse_args()

    import sys
    sys.path.append(args.repo)
    convert(args.pkl, args.out)


if __name__ == "__main__":
    main()
