from os.path import join, dirname
import tarfile

ARCHIVE_NAME = 'pmr2hgtest.tgz'
ARCHIVE_PATH = join(dirname(__file__), ARCHIVE_NAME)
ARCHIVE_REVS = [
    'eb2615b6ebf9a44226bba22c766bc7858e370ed9',
    'c7888f70e7ee440a561283bb7a27cc5ba9888a58',
    'd52a32a5fa62a357ed77314888b939f0fc7c9c9b',
    'd2759ae2454c4e0946f4d8feee60864590b2ddb0',
    '0ab9d678be937c20c3ba4953ba49515fdad396e7',
    'c9226c3a085546313d61413adb95d3a9da2294e0',
    'f3464eef175a56df0cd462dc6799653bb0f760be',
    '98a09b3682f1ba24bc9e873fea335cbe6e10e66e',
]

def extract_archive(path, archive_path=ARCHIVE_PATH):
    # extraction 
    tf = tarfile.open(archive_path, 'r:gz')
    mem = tf.getmembers()
    for m in mem:
        tf.extract(m, path)
    tf.close()
