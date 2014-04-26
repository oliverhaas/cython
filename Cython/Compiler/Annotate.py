# Note: Work in progress

import os
import re
import codecs
from xml.sax.saxutils import escape as html_escape
from StringIO import StringIO

import Version
from Code import CCodeWriter
from Cython import Utils


class AnnotationCCodeWriter(CCodeWriter):

    def __init__(self, create_from=None, buffer=None, copy_formatting=True):
        CCodeWriter.__init__(self, create_from, buffer, copy_formatting=True)
        if create_from is None:
            self.annotation_buffer = StringIO()
            self.annotations = []
            self.last_pos = None
            self.code = {}
        else:
            # When creating an insertion point, keep references to the same database
            self.annotation_buffer = create_from.annotation_buffer
            self.annotations = create_from.annotations
            self.code = create_from.code
            self.last_pos = create_from.last_pos

    def create_new(self, create_from, buffer, copy_formatting):
        return AnnotationCCodeWriter(create_from, buffer, copy_formatting)

    def write(self, s):
        CCodeWriter.write(self, s)
        self.annotation_buffer.write(s)

    def mark_pos(self, pos):
        if pos is not None:
            CCodeWriter.mark_pos(self, pos)
        if self.last_pos:
            pos_code = self.code.setdefault(self.last_pos[0].filename,{})
            code = pos_code.get(self.last_pos[1], "")
            pos_code[self.last_pos[1]] = code + self.annotation_buffer.getvalue()
        self.annotation_buffer = StringIO()
        self.last_pos = pos

    def annotate(self, pos, item):
        self.annotations.append((pos, item))

    def _css(self):
        """css template will later allow to choose a colormap"""
        css = [self._css_template]
        for i in range(255):
            color = u"FFFF%02x" % int(255/(1+i/10.0))
            css.append('\n.cython.score-%d {background-color: #%s;}' % (i, color))

        return ''.join(css)

    _js = """
    function toggleDiv(id) {
        theDiv = id.nextElementSibling
        if (theDiv.style.display != 'block') theDiv.style.display = 'block';
        else theDiv.style.display = 'none';
    }
    """

    _css_template = """

body { font-family: courier; font-size: 12; }

.cython.code  { font-size: 9; color: #444444; display: none; margin-left: 20px; }
.cython.py_c_api  { color: red; }
.cython.py_macro_api  { color: #FF7000; }
.cython.pyx_c_api  { color: #FF3000; }
.cython.pyx_macro_api  { color: #FF7000; }
.cython.refnanny  { color: #FFA000; }

.cython.error_goto  { color: #FFA000; }

.cython.tag  {  }

.cython.coerce  { color: #008000; border: 1px dotted #008000 }

.cython.py_attr { color: #FF0000; font-weight: bold; }
.cython.c_attr  { color: #0000FF; }

.cython.py_call { color: #FF0000; font-weight: bold; }
.cython.c_call  { color: #0000FF; }

.cython.line { margin: 0em }

"""

    def save_annotation(self, source_filename, target_filename):
        with Utils.open_source_file(source_filename) as f:
            lines = f.readlines()
        code_source_file = self.code.get(source_filename, {})
        c_file = Utils.decode_filename(os.path.basename(target_filename))
        html_filename = os.path.splitext(target_filename)[0] + ".html"
        with codecs.open(html_filename, "w", encoding="UTF-8") as out_buffer:
            out_buffer.write(self._save_annotation(lines, code_source_file , c_file))

    def _save_annotation_header(self, c_file):
        outlist = []
        outlist.append(u'<!DOCTYPE html>\n')
        outlist.append(u'<!-- Generated by Cython %s -->\n' % Version.watermark)
        outlist.append(u'<html>\n')
        outlist.append(u"""
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <style type="text/css">
        {css}
    </style>
    <script>
        {js}
    </script>
</head>
        """.format(css=self._css(), js=self._js))
        outlist.append(u'<body>\n')
        outlist.append(u'<p>Generated by Cython %s</p>\n' % Version.watermark)
        if c_file :
            outlist.append(u'<p>Raw output: <a href="%s">%s</a></p>\n' % (c_file, c_file))
        return outlist

    def _save_annotation_footer(self):
        return (u'</body></html>\n',)

    def _save_annotation(self, lines, code_source_file , c_file=None):
        """
        lines : original cython source code split by lines
        code_source_file : generated c code keyed by line number in original file
        target filename : name of the file in which to store the generated html
        c_file : filename in which the c_code has been written

        """

        outlist = []
        outlist.extend(self._save_annotation_header(c_file))

        outlist.extend(self._save_annotation_body(lines, code_source_file , c_file=None))
        outlist.extend(self._save_annotation_footer())
        return ''.join(outlist)

    def _save_annotation_body(self, lines, code_source_file , c_file=None):
        outlist=[]
        pos_comment_marker = u'/* \N{HORIZONTAL ELLIPSIS} */\n'
        zero_calls = dict((name, 0) for name in
                          'refnanny py_macro_api py_c_api pyx_macro_api pyx_c_api error_goto'.split())

        self.mark_pos(None)

        def annotate(match):
            group_name = match.lastgroup
            calls[group_name] += 1
            return ur"<span class='cython %s'>%s</span>" % (
                group_name, match.group(group_name))

        for k, line in enumerate(lines, 1):
            line = html_escape(line)
            try:
                code = code_source_file[k]
            except KeyError:
                code = ''
            else:
                code = _replace_pos_comment(pos_comment_marker, code)
                if code.startswith(pos_comment_marker):
                    code = code[len(pos_comment_marker):]
                code = html_escape(code)

            calls = zero_calls.copy()
            code = _parse_code(annotate, code)
            score = (5 * calls['py_c_api'] + 2 * calls['pyx_c_api'] +
                     calls['py_macro_api'] + calls['pyx_macro_api'])

            outlist.append(u"<pre class='cython line score-%s' onclick='toggleDiv(this)'>" % (score))

            outlist.append(u" %d: " % k)
            outlist.append(line.rstrip())

            outlist.append(u'</pre>\n')
            outlist.append(u"<pre class='cython code score-%s' >%s</pre>" % (score, code))
        return outlist


_parse_code = re.compile(
    ur'(?P<refnanny>__Pyx_X?(?:GOT|GIVE)REF|__Pyx_RefNanny[A-Za-z]+)|'
    ur'(?:'
    ur'(?P<pyx_macro_api>__Pyx_[A-Z][A-Z_]+)|'
    ur'(?P<pyx_c_api>__Pyx_[A-Z][a-z_][A-Za-z_]+)|'
    ur'(?P<py_macro_api>Py[A-Z][a-z]+_[A-Z][A-Z_]+)|'
    ur'(?P<py_c_api>Py[A-Z][a-z]+_[A-Z][a-z][A-Za-z_]+)'
    ur')(?=\()|'       # look-ahead to exclude subsequent '(' from replacement
    ur'(?P<error_goto>(?:(?<=;) *if .* +)?\{__pyx_filename = .*goto __pyx_L\w+;\})'
).sub


_replace_pos_comment = re.compile(
    # this matches what Cython generates as code line marker comment
    ur'^\s*/\*(?:(?:[^*]|\*[^/])*\n)+\s*\*/\s*\n',
    re.M
).sub


class AnnotationItem(object):

    def __init__(self, style, text, tag="", size=0):
        self.style = style
        self.text = text
        self.tag = tag
        self.size = size

    def start(self):
        return u"<span class='cython tag %s' title='%s'>%s" % (self.style, self.text, self.tag)

    def end(self):
        return self.size, u"</span>"
