# -*- coding: utf-8 -*-
"""
Created on Fri Nov 11 14:38:15 2022

"""


from tqdm import tqdm
import numpy as np
import scipy.stats
from bert4keras.backend import keras, K
from bert4keras.tokenizers import Tokenizer
from bert4keras.models import build_transformer_model
from bert4keras.snippets import open, sequence_padding
from keras.models import Model
from bert_whitening.hyperparameters import Hyperparamters as hp



def get_tokenizer(dict_path):
    """
    建立分词器
    """
    return Tokenizer(dict_path, do_lower_case=True)


def get_encoder(config_path, 
                checkpoint_path, 
                model='bert', 
                pooling='first-last-avg'):
    """
    获取编码器
    """
    assert pooling in ['first-last-avg', 'last-avg', 'cls', 'pooler']
    
    if pooling == 'pooler':
        bert = build_transformer_model(
            config_path, checkpoint_path, model=model, with_pool='linear'
        )
    else:
        bert = build_transformer_model(
            config_path, checkpoint_path, model=model
        )
    # print('1'*20) 
    encoder_layers, count = [], 0
    while True:
        try:
            output = bert.get_layer(
                'Transformer-%d-FeedForward-Norm' % count
            ).output
            encoder_layers.append(output)
            count += 1
        except:
            break
    # print('2'*20) 
    # print('3'*20,encoder_layers[0][0])#(?, 768)
    # print('4'*20,len(encoder_layers))#12
    # print('5'*20,encoder_layers[0].shape)#(?, ?, 768)
    # print(type(encoder_layers[0]))
    if pooling == 'first-last-avg':
        outputs = [
            keras.layers.GlobalAveragePooling1D()(encoder_layers[0]),
            keras.layers.GlobalAveragePooling1D()(encoder_layers[-1])
        ]
        # print('6'*20) 
        output = keras.layers.Average()(outputs)
    elif pooling == 'last-avg':
        output = keras.layers.GlobalAveragePooling1D()(encoder_layers[-1])
    elif pooling == 'cls':
        output = keras.layers.Lambda(lambda x: x[:, 0])(encoder_layers[-1])
    elif pooling == 'pooler':
        output = bert.output
    # print('7'*20) 
    encoder = Model(bert.inputs, output)
    return encoder


def convert_sentence_to_ids(sentence, tokenizer, maxlen=hp.maxlen):
    """
    转换文本数据为id形式
    """
    a_token_ids = []
    token_ids = tokenizer.encode(sentence, max_length=maxlen)[0]
    a_token_ids.append(token_ids)
    a_token_ids = sequence_padding(a_token_ids)
    return a_token_ids


def convert_sentences_to_ids(sentences, tokenizer, maxlen=hp.maxlen):
    """
    转换文本数据为id形式
    """
    token_ids_list = []
    for sentence in tqdm(sentences):
        token_ids = tokenizer.encode(sentence, max_length=maxlen)[0]
        token_ids_list.append(token_ids)
    token_ids_output = sequence_padding(token_ids_list)
    return token_ids_output


def convert_sentence_to_vecs(sentence, tokenizer, encoder):
    """
    转换文本数据为向量形式
    """
    a_token_ids = convert_sentence_to_ids(sentence, tokenizer)
    a_vecs = encoder.predict([a_token_ids,
                              np.zeros_like(a_token_ids)],
                             verbose=True)
    return a_vecs


def convert_sentences_to_vecs(sentences, tokenizer, encoder):
    """
    转换文本数据为向量形式
    """
    a_token_ids_list = convert_sentences_to_ids(sentences, tokenizer)
    print('a_token_ids_list:',a_token_ids_list.shape)
    a_vecs = encoder.predict([a_token_ids_list,
                              np.zeros_like(a_token_ids_list)],
                             verbose=True)
    return a_vecs


def convert_to_ids(data, tokenizer, maxlen=hp.maxlen):
    """转换文本数据为id形式
    """
    a_token_ids, b_token_ids, labels, query1, query2 = [], [], [], [], []
    for d in tqdm(data):
        token_ids = tokenizer.encode(d[0], max_length=maxlen)[0]
        a_token_ids.append(token_ids)
        query1.append(d[0])
        token_ids = tokenizer.encode(d[1], max_length=maxlen)[0]
        b_token_ids.append(token_ids)
        query2.append(d[1])
        labels.append(d[2])
    a_token_ids = sequence_padding(a_token_ids)
    b_token_ids = sequence_padding(b_token_ids)
    return a_token_ids, b_token_ids, labels, query1, query2


def convert_to_vecs(data, tokenizer, encoder, maxlen=hp.maxlen):
    """
    转换文本数据为向量形式
    """
    a_token_ids, b_token_ids, labels, query1, query2 = convert_to_ids(data, tokenizer, maxlen)
    a_vecs = encoder.predict([a_token_ids,
                              np.zeros_like(a_token_ids)],
                             verbose=True)
    b_vecs = encoder.predict([b_token_ids,
                              np.zeros_like(b_token_ids)],
                             verbose=True)
    return a_vecs, b_vecs, np.array(labels), query1, query2


def compute_kernel_bias(vecs):
    """
    计算kernel和bias
    最后的变换：y = (x + bias).dot(kernel)
    """
    vecs = np.concatenate(vecs, axis=0)
    mu = vecs.mean(axis=0, keepdims=True)
    cov = np.cov(vecs.T)
    u, s, vh = np.linalg.svd(cov)
    W = np.dot(u, np.diag(1 / np.sqrt(s)))
    return W[:, :hp.k], -mu


def transform_and_normalize(vecs, kernel=None, bias=None):
    """
    应用变换，然后标准化
    """
    if not (kernel is None or bias is None):
        vecs = (vecs + bias).dot(kernel)
    norms = (vecs ** 2).sum(axis=1, keepdims=True) ** 0.5
    return vecs / np.clip(norms, 1e-8, np.inf)


def compute_corrcoef(x, y):
    """
    Spearman相关系数
    """
    return scipy.stats.spearmanr(x, y).correlation






import tensorflow as tf
from keras.engine.base_layer import Layer
from keras.engine.base_layer import InputSpec


class _GlobalPooling1D(Layer):
    """Abstract class for different global pooling 1D layers.
    """

    def __init__(self, data_format='channels_last', **kwargs):
        super(_GlobalPooling1D, self).__init__(**kwargs)
        self.input_spec = InputSpec(ndim=3)
        self.data_format = K.normalize_data_format(data_format)

    def compute_output_shape(self, input_shape):
        if self.data_format == 'channels_first':
            return (input_shape[0], input_shape[1])
        else:
            return (input_shape[0], input_shape[2])

    def call(self, inputs):
        raise NotImplementedError

    def get_config(self):
        config = {'data_format': self.data_format}
        base_config = super(_GlobalPooling1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class GlobalAveragePooling1D(_GlobalPooling1D):
    """Global average pooling operation for temporal data.

    # Arguments
        data_format: A string,
            one of `channels_last` (default) or `channels_first`.
            The ordering of the dimensions in the inputs.
            `channels_last` corresponds to inputs with shape
            `(batch, steps, features)` while `channels_first`
            corresponds to inputs with shape
            `(batch, features, steps)`.

    # Input shape
        - If `data_format='channels_last'`:
            3D tensor with shape:
            `(batch_size, steps, features)`
        - If `data_format='channels_first'`:
            3D tensor with shape:
            `(batch_size, features, steps)`

    # Output shape
        2D tensor with shape:
        `(batch_size, features)`
    """

    def __init__(self, data_format='channels_last', **kwargs):
        super(GlobalAveragePooling1D, self).__init__(data_format,
                                                     **kwargs)
        self.supports_masking = True

    def call(self, inputs, mask=None):
        steps_axis = 1 if self.data_format == 'channels_last' else 2
        if mask is not None:
            mask = K.cast(mask, K.floatx())
            mask = K.reshape(mask, [-1,tf.shape(inputs)[1],1])
            inputs *= mask
            return K.sum(inputs, axis=steps_axis) / K.sum(mask, axis=steps_axis)
        else:
            return K.mean(inputs, axis=steps_axis)

    def compute_mask(self, inputs, mask=None):
        return None
    
    
    
    
    
