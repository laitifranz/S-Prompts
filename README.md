# S-Prompts Learning with Pre-trained Transformers: An Occam’s Razor for Domain Incremental Learning

## Improvement made by me:
- Add pip requirements.txt without using conda
- Add eval directly in this repo without relying on the addition repo (bugged)
- Fix bugs related to one GPU usage
- Fix bugs related to args of ML/DL frameworks
- Save model as state_dict instead of the full model
- Clean code and fix problems

<div align="justify">
  This is the official implementation of our NeurIPS 2022 paper "S-Prompts Learning with Pre-trained Transformers: An Occam’s Razor for Domain Incremental Learning".
In this paper, we propose one simple paradigm (named as S-Prompting) and two concrete approaches. The best of the proposed approaches achieves a remarkable relative improvement (an average of about 30%) over the best of the state-of-the-art exemplar-free methods for three standard Domain Incremental Learning (DIL) tasks.
</div>


**S-Prompts Learning with Pre-trained Transformers: An Occam’s Razor for Domain Incremental Learning** <br>
Yabin Wang, Zhiwu Huang, Xiaopeng Hong. 2022 Conference on Neural Information Processing Systems (NeurIPS 22). <br>
[[Paper]](https://openreview.net/pdf?id=ZVe_WeMold)

## Introduction

<div align="justify">
S-Prompts introduce a rule-breaking idea to play a win-win game for domain incremental learning.
Specifically, S-Prompts uses a new prompting paradigm that learns the prompts independently domain by domain, and incrementally inserts the learned prompts in a pool.
The learning process only requests the most naive cross-entropy loss for supervision. 
The inference is also simple and efficient. 
It simply uses K-NN to search for the nearest domain center generated by K-Means on the training data to the features of the given test sample, followed by prepending the learned domain-associated prompts with the image tokens to the transformer for the final classification. 
As S domain-related prompts will be finally learned independently, where S is the total number of domains, we name the proposed paradigm as S-Prompts or S-Prompting for simplicity throughout the paper. 
We hope the proposed S-Prompting becomes an Occam’s Razor (i.e., a simple and elegant principle) for DIL.
</div>



## Enviroment setup
Create the virtual environment for S-Prompts.
```python
conda env create -f environment.yaml
```
After this, you will get a new environment **sp** that can conduct S-Prompts experiments.  
Run `conda activate sp` to activate.

Note that only NVIDIA GPUs are supported for now, and we use NVIDIA RTX 3090. 

## Dataset preparation
Please refer to the following links to download three standard domain incremental learning benchmark datasets. 

[CDDB](https://github.com/Coral79/CDDB)  
[CORe50](https://vlomonaco.github.io/core50/index.html#dataset)  
[DomainNet](http://ai.bu.edu/M3SDA/)  

Unzip the downloaded files, and you will get the following folders.
```
CDDB
├── biggan
│   ├── train
│   └── val
├── gaugan
│   ├── train
│   └── val
├── san
│   ├── train
│   └── val
├── whichfaceisreal
│   ├── train
│   └── val
├── wild
│   ├── train
│   └── val
... ...
```

```
core50
└── core50_128x128
    ├── labels.pkl
    ├── LUP.pkl
    ├── paths.pkl
    ├── s1
    ├── s2
    ├── s3
    ...
```

```
domainnet
├── clipart
│   ├── aircraft_carrier
│   ├── airplane
│   ... ...
├── clipart_test.txt
├── clipart_train.txt
├── infograph
│   ├── aircraft_carrier
│   ├── airplane
│   ... ...
├── infograph_test.txt
├── infograph_train.txt
├── painting
│   ├── aircraft_carrier
│   ├── airplane
│   ... ...
... ...
```


## Training:

Please change the `data_path` in the config files to the locations of the datasets。  

Currently, there are two options for `net_type` in the config files: `slip` and `sip`.  
`slip` means S-liPrompts and `sip` means S-iPrompts.  

Feel free to change the parameters in the config files, following scripts will reproduce the main results in our paper.

### CDDB:
```
python main.py --config configs/cddb_slip.json
python main.py --config configs/cddb_sip.json
```

### CORe50:
```
python main.py --config configs/core50_slip.json
```

### DomainNet:
```
python main.py --config configs/domainnet_slip.json
```



## License

Please check the MIT  [license](./LICENSE) that is listed in this repository.