'''
A script to convert TMXs into parallel corpuses for machine
translation (e.g. Moses: http://www.statmt.org/moses/) training.

Pass in either paths to TMX files, or directories containing TMX files.
The script will recursively traverse directories and process all TMXs.

To perform tokenization or to filter the output, use the convert() method
with subclasses of the Tokenizer or Filter objects.

@author: aaron.madlon-kay
'''

import argparse
import sys
import os
import codecs
import logging
from tokenizer import DEFAULT_TOKENIZER, PyJaTokenizer
from xml.etree import ElementTree
from HTMLParser import HTMLParser


class Converter(object):
    def __init__(self):
        self.tokenizers = {}
        self.filters = []
        self.suppress_count = 0
        self.output_lines = 0
        self.output_files = {}
        self.output_path = os.getcwd()
        logging.debug('Output path: %s', self.output_path)
    
    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        cleanup(self.output_files)
        
    def add_tokenizers(self, tokenizers):
        for tokenizer in tokenizers:
            self.tokenizers[tokenizer.lang] = tokenizer
            
    def add_filter(self, bitext_filter):
        if bitext_filter is not None:
            self.filters.append(bitext_filter)
            
    def convert(self, files):
        self.suppress_count = 0
        self.output_lines = 0
        for tmx in files:
            print('Extracting %s' % os.path.basename(tmx))
            for bitext in extract_tmx(tmx):
                self.__output(bitext)
        logging.info('Output %d pairs', self.output_lines)
        if self.suppress_count:
            logging.info('Suppressed %d pairs', self.suppress_count)
            
    def __output(self, bitext):
        for fltr in self.filters:
            if not fltr.filter(bitext):
                self.suppress_count += 1
                return
            
        for lang, text in bitext.items():
            tokenizer = self.tokenizers.get(lang, DEFAULT_TOKENIZER)
            bitext['tok.' + lang] = tokenizer.tokenize(text)
            
        for lang in bitext.keys():
            if lang not in self.output_files.keys():
                self.output_files[lang] = codecs.open(os.path.join(self.output_path, 'bitext.' + lang),
                                                      'w',
                                                      encoding='utf-8')
        for lang, text in bitext.items():
            out_file = self.output_files[lang]
            out_file.write(text)
            out_file.write('\n')

        self.output_lines += 1


def get_files(path, ext):
    for root, dirs, files in os.walk(path):
        for a_file in files:
            if a_file.endswith(ext):
                yield os.path.join(root, a_file)


def extract_tmx(tmx):
    for event, elem in ElementTree.iterparse(tmx):
        if elem.tag == 'tu':
            bitext = extract_tu(elem)
            if bitext:
                yield bitext


def extract_tu(tu):
    bitext = {}
    for tuv in tu.findall('tuv'):
        lang, text = extract_tuv(tuv)
        if None not in (lang, text):
            bitext[lang] = text
    if len(bitext) != 2:
        logging.debug('TU had %d TUV(s). Skipping.', len(bitext))
        logging.debug('\t' + ElementTree.tostring(tu))
        return {}
    return bitext


def extract_tuv(tuv):
    lang = tuv.attrib.get('lang', None)
    if lang == None:
        lang = tuv.attrib.get('{http://www.w3.org/XML/1998/namespace}lang', None)
    if lang == None:
        logging.debug('TUV missing lang. Skipping.')
        return None, None
    lang = normalize_lang(lang)
    segs = tuv.findall('seg')
    if len(segs) > 1:
        logging.debug('Multiple segs found in TUV. Skipping.')
        return None, None
    text = extract_seg(segs[0])
    if text is None:
        logging.debug('TUV missing seg. Skipping.')
        return None, None
    text = clean_text(text)
    if not text:
        logging.debug('TUV had blank seg. Skipping.')
        return None, None
    return lang, text


def extract_seg(seg):
    buffer = [seg.text]
    for child in seg.getchildren():
        buffer.append(child.text)
        buffer.append(child.tail)
    return ''.join([piece for piece in buffer if piece != None])


HTML_PARSER = HTMLParser()

def clean_text(text):
    text = text.strip().replace('\n', '').replace('\r', '')
    return HTML_PARSER.unescape(text)


def normalize_lang(lang):
    result = lang.lower()
    if len(result) > 2 and result[2] in ('-', '_'):
        result = result[:2]
    return result


def cleanup(output_files):
    for lang, out_file in output_files.items():
        out_file.close()


def convert(paths, tokenizers=[], bitext_filter=None):
    files = set()
    for path in sorted(set(os.path.abspath(p) for p in paths)):
        if os.path.isdir(path):
            tmxs = set(get_files(path, '.tmx'))
            logging.info('Queuing %d TMX(s) in %s', len(tmxs), path)
            files |= tmxs
        elif os.path.isfile(path) and path.endswith('.tmx'):
            files.add(path)
    if files:
        with Converter() as converter:
            converter.add_tokenizers(tokenizers)
            converter.add_filter(bitext_filter)
            converter.convert(sorted(files))
    else:
        logging.error('Please specify input files or paths.')
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description='Convert TMX files to '
                                     'flat corpus files')
    parser.add_argument('--verbose', '-v', action='count', default=0)
    parser.add_argument('path', nargs='+')
    args = parser.parse_args()

    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(len(levels) - 1, args.verbose)]
    logging.getLogger().setLevel(level)

    return convert(args.path, tokenizers=[PyJaTokenizer()])

if __name__ == '__main__':
    sys.exit(main())
