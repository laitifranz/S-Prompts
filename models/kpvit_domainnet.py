"""
This is the domain incremental learning for our methods using CORe50 dataset.
"""


import os.path as osp
import threadpoolctl
import copy

import torch
import torch.nn as nn
from torch.nn import functional as F
from torch.cuda.amp import GradScaler, autocast

from utils.latencyTools.DomainNet_dataset.domainnetwords import domainnet_classnames
from operator import itemgetter



from convs.vit import VisionTransformer, PatchEmbed, Block,resolve_pretrained_cfg, build_model_with_cfg, checkpoint_filter_fn

class ViT_KPrompts(VisionTransformer):
    def __init__(
            self, img_size=224, patch_size=16, in_chans=3, num_classes=1000, global_pool='token',
            embed_dim=768, depth=12, num_heads=12, mlp_ratio=4., qkv_bias=True, representation_size=None,
            drop_rate=0., attn_drop_rate=0., drop_path_rate=0., weight_init='', init_values=None,
            embed_layer=PatchEmbed, norm_layer=None, act_layer=None, block_fn=Block):

        super().__init__(img_size=img_size, patch_size=patch_size, in_chans=in_chans, num_classes=num_classes, global_pool=global_pool,
            embed_dim=embed_dim, depth=depth, num_heads=num_heads, mlp_ratio=mlp_ratio, qkv_bias=qkv_bias, representation_size=representation_size,
            drop_rate=drop_rate, attn_drop_rate=attn_drop_rate, drop_path_rate=drop_path_rate, weight_init=weight_init, init_values=init_values,
            embed_layer=embed_layer, norm_layer=norm_layer, act_layer=act_layer, block_fn=block_fn)


    def forward(self, x, instance_tokens=None, **kwargs):
        x = self.patch_embed(x)
        x = torch.cat((self.cls_token.expand(x.shape[0], -1, -1), x), dim=1)

        if instance_tokens is not None:
            instance_tokens = instance_tokens.to(x.dtype) + torch.zeros(x.shape[0], 1, x.shape[-1], dtype=x.dtype, device=x.device)

        x = x + self.pos_embed.to(x.dtype)
        if instance_tokens is not None:
            x = torch.cat([x[:,:1,:], instance_tokens, x[:,1:,:]], dim=1)

        x = self.pos_drop(x)
        x = self.blocks(x)
        x = self.norm(x)
        if self.global_pool:
            x = x[:, 1:].mean(dim=1) if self.global_pool == 'avg' else x[:, 0]
        x = self.fc_norm(x)
        return x



def _create_vision_transformer(variant, pretrained=False, **kwargs):
    if kwargs.get('features_only', None):
        raise RuntimeError('features_only not implemented for Vision Transformer models.')

    # NOTE this extra code to support handling of repr size for in21k pretrained models
    pretrained_cfg = resolve_pretrained_cfg(variant, kwargs=kwargs)
    default_num_classes = pretrained_cfg['num_classes']
    num_classes = kwargs.get('num_classes', default_num_classes)
    repr_size = kwargs.pop('representation_size', None)
    if repr_size is not None and num_classes != default_num_classes:
        repr_size = None

    model = build_model_with_cfg(
        ViT_KPrompts, variant, pretrained,
        pretrained_cfg=pretrained_cfg,
        representation_size=repr_size,
        pretrained_filter_fn=checkpoint_filter_fn,
        pretrained_custom_load='npz' in pretrained_cfg['url'],
        **kwargs)
    return model


class KPromptNet(nn.Module):

    def __init__(self):
        super(KPromptNet, self).__init__()

        model_kwargs = dict(patch_size=16, embed_dim=768, depth=12, num_heads=12)

        self.image_encoder =_create_vision_transformer('vit_base_patch16_224', pretrained=True, **model_kwargs)


        self.prompt_list = []

        self.prompt_pool = nn.ModuleList([
            nn.Linear(768, 345, bias=True),
            nn.Linear(768, 345, bias=True),
            nn.Linear(768, 345, bias=True),
            nn.Linear(768, 345, bias=True),
            nn.Linear(768, 345, bias=True),
            nn.Linear(768, 345, bias=True),
        ])

        self.instance_prompt = nn.ModuleList([
            nn.Linear(768, 10, bias=False),
            nn.Linear(768, 10, bias=False),
            nn.Linear(768, 10, bias=False),
            nn.Linear(768, 10, bias=False),
            nn.Linear(768, 10, bias=False),
            nn.Linear(768, 10, bias=False),
        ])

        self.instance_keys = nn.Linear(768, 10, bias=False)

        self.numtask = 0

    @property
    def feature_dim(self):
        return self.image_encoder.out_dim

    def extract_vector(self, image):

        image_features = self.image_encoder(image)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        return image_features

    def forward(self, image):
        logits = []
        image_features = self.image_encoder(image, self.instance_prompt[self.numtask - 1].weight)
        # image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        for prompt in [self.prompt_pool[self.numtask - 1]]:
            # text_features = prompts.weight
            # text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            # logits.append(image_features @ text_features.t())
            logits.append(prompt(image_features))

        return {
            'logits': torch.cat(logits, dim=1),
            'features': image_features
        }

    def interface(self, image, selection):
        instance_batch = torch.stack([i.weight for i in self.instance_prompt], 0)[selection, :, :]
        image_features = self.image_encoder(image, instance_batch)
        # image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        logits = []
        for prompt in self.prompt_pool:
            # text_features = prompt.weight
            # text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            # logits.append(image_features @ text_features.t())
            logits.append(prompt(image_features))

        logits = torch.cat(logits, 1)
        selectedlogit = []
        for idx, ii in enumerate(selection):
            selectedlogit.append(logits[idx][345*ii:345*ii+345])
        selectedlogit = torch.stack(selectedlogit)
        return selectedlogit

    def update_fc(self, nb_classes):
        self.numtask += 1
        pass

    def copy(self):
        return copy.deepcopy(self)

    def freeze(self):
        for param in self.parameters():
            param.requires_grad = False
        self.eval()

        return self

from models.base import BaseLearner
import logging
import numpy as np
from torch.utils.data import DataLoader
from torch import optim
from tqdm import tqdm
from utils.toolkit import  tensor2numpy
from utils.toolkit import accuracy_binary, accuracy, accuracy_domain
from utils.latencyTools.DomainNet_dataset.data_loader import DomainNet_dataset


class kpvit_domainnet(BaseLearner):

    def __init__(self, args):
        super().__init__(args)
        self._network = KPromptNet()
        self.args = args
        self.EPSILON = args["EPSILON"]
        self.init_epoch = args["init_epoch"]
        self.init_lr = args["init_lr"]
        self.init_milestones = args["init_milestones"]
        self.init_lr_decay = args["init_lr_decay"]
        self.init_weight_decay = args["init_weight_decay"]
        self.epochs = args["epochs"]
        self.lrate = args["lrate"]
        self.milestones = args["milestones"]
        self.lrate_decay = args["lrate_decay"]
        self.batch_size = args["batch_size"]
        self.weight_decay = args["weight_decay"]
        self.num_workers = args["num_workers"]
        self.T = args["T"]

        self.all_keys = []

        # self.domainlist = ['clipart','quickdraw','painting','sketch','infograph','clipart']
        self.domainlist = ['real','quickdraw','painting','sketch','infograph','clipart']

    def after_task(self):
        self._old_network = self._network.copy().freeze()
        logging.info('Exemplar size: {}'.format(self.exemplar_size))
        self._known_classes = self._total_classes

        del self.train_loader, self.test_loader


    def incremental_train(self, data_manager):
        self._cur_task += 1
        self._network.update_fc(self._total_classes)

        logging.info('Learning on {}'.format(self._cur_task))

        train_dataset = DomainNet_dataset(domain_names=self.domainlist[self._cur_task], mode='train')
        # train_dataset = DomainNet_dataset(domain_names=None, mode='train') # for joint training
        self.train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True, num_workers=self.num_workers)

        test_dataset = DomainNet_dataset(domain_names=None, mode='test')
        self.test_loader = DataLoader(test_dataset, batch_size=self.batch_size, shuffle=False, num_workers=self.num_workers)
        if len(self._multiple_gpus) > 1:
            self._network = nn.DataParallel(self._network, self._multiple_gpus)
        self._train(self.train_loader, self.test_loader)

        self.clustering(self.train_loader)

        if len(self._multiple_gpus) > 1:
            self._network = self._network.module

    def _train(self, train_loader, test_loader):
        self._network.to(self._device)
        if self._old_network is not None:
            self._old_network.to(self._device)

        for name, param in self._network.named_parameters():
            param.requires_grad_(False)
            if "instance_prompt"+"."+str(self._network.module.numtask-1) in name:
                param.requires_grad_(True)
            if "instance_keys" in name:
                param.requires_grad_(True)
            if "prompt_pool"+"."+str(self._network.module.numtask-1) in name:
                param.requires_grad_(True)
        # Double check
        enabled = set()
        for name, param in self._network.named_parameters():
            if param.requires_grad:
                enabled.add(name)
        print(f"Parameters to be updated: {enabled}")

        optimizer = optim.SGD(self._network.parameters(), momentum=0.9,lr=self.init_lr,weight_decay=self.init_weight_decay)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer=optimizer,T_max=self.init_epoch)
        self._init_train(train_loader,test_loader,optimizer,scheduler)

    def _init_train(self,train_loader,test_loader,optimizer,scheduler):
        prog_bar = tqdm(range(self.init_epoch))
        for _, epoch in enumerate(prog_bar):
            self._network.eval()
            losses = 0.
            correct, total = 0, 0
            for i, (_, inputs, targets) in enumerate(train_loader):
                inputs, targets = inputs.to(self._device), targets.to(self._device)
                logits = self._network(inputs)['logits']
                loss=F.cross_entropy(logits,targets)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                losses += loss.item()

                _, preds = torch.max(logits, dim=1)
                correct += preds.eq(targets.expand_as(preds)).cpu().sum()
                total += len(targets)

            scheduler.step()
            train_acc = np.around(tensor2numpy(correct)*100 / total, decimals=2)

            # test_acc = self._compute_accuracy(self._network, test_loader)
            test_acc = 0
            info = 'Task {}, Epoch {}/{} => Loss {:.3f}, Train_accy {:.2f}, Test_accy {:.2f}'.format(
            self._cur_task, epoch+1, self.init_epoch, losses/len(train_loader), train_acc, test_acc)
            prog_bar.set_description(info)

        logging.info(info)


    def clustering(self, dataloader):
        from sklearn.cluster import KMeans

        features = []
        for i, (_, inputs, targets) in enumerate(dataloader):
            inputs, targets = inputs.to(self._device), targets.to(self._device)
            # only get new data
            mask = (targets >= self._known_classes).nonzero().view(-1)
            inputs = torch.index_select(inputs, 0, mask)
            with torch.no_grad():
                if isinstance(self._network, nn.DataParallel):
                    feature = self._network.module.extract_vector(inputs)
                else:
                    feature = self._network.extract_vector(inputs)
            feature = feature / feature.norm(dim=-1, keepdim=True)
            features.append(feature)
        features = torch.cat(features, 0).cpu().detach().numpy()
        clustering = KMeans(n_clusters=10, random_state=0).fit(features)
        self.all_keys.append(torch.tensor(clustering.cluster_centers_).to(feature.device))
        del clustering, features


    def _evaluate(self, y_pred, y_true):
        ret = {}
        grouped = accuracy_domain(y_pred.T[0], y_true, self._known_classes)
        ret['grouped'] = grouped
        ret['top1'] = grouped['total']
        ret['top{}'.format(self.topk)] = np.around((y_pred.T == np.tile(y_true, (self.topk, 1))).sum()*100/len(y_true),
                                                   decimals=2)

        return ret


    def _eval_cnn(self, loader):
        self._network.eval()
        y_pred, y_true = [], []
        for _, (_, inputs, targets) in enumerate(loader):
            inputs = inputs.to(self._device)
            targets = targets.to(self._device)

            with torch.no_grad():
                if isinstance(self._network, nn.DataParallel):
                    feature = self._network.module.extract_vector(inputs)
                else:
                    feature = self._network.extract_vector(inputs)
                taskselection = []
                for task_centers in self.all_keys:
                    tmpcentersbatch = []
                    for center in task_centers:
                        tmpcentersbatch.append((((feature - center) ** 2) ** 0.5).sum(1))
                    taskselection.append(torch.vstack(tmpcentersbatch).min(0)[0])

                # import pdb;pdb.set_trace()
                selection = torch.vstack(taskselection).min(0)[1]
                # print("Kmeans分类正确率：{:.3f}".format(sum(selection == ((targets/10).int()))/len(targets)))

                if isinstance(self._network, nn.DataParallel):
                    outputs = self._network.module.interface(inputs, selection)
                else:
                    outputs = self._network.interface(inputs, selection)

            predicts = torch.topk(outputs, k=self.topk, dim=1, largest=True, sorted=True)[1]  # [bs, topk]
            # predicts = predicts + (selection * 10).unsqueeze(1)
            y_pred.append(predicts.cpu().numpy())
            y_true.append(targets.cpu().numpy())

        return np.concatenate(y_pred), np.concatenate(y_true)  # [N, topk]





def _KD_loss(pred, soft, T):
    pred = torch.log_softmax(pred/T, dim=1)
    soft = torch.softmax(soft/T, dim=1)
    return -1 * torch.mul(soft, pred).sum()/pred.shape[0]