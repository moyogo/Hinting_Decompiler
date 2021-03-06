from parser import AssemblyParser, ParseException

from fontTools.ttLib import (TTFont, TTLibError)
from fontTools.ttLib.tables.ttProgram import Program

class VTTLibError(TTLibError):
    pass

def tokenize(data, parseAll=True):
    return AssemblyParser.parseString(data, parseAll=parseAll)

def get_glyph_assembly(font, name):
    return get_vtt_program(font, name, is_glyph=True)

def get_glyph_talk(font, name):
    return get_vtt_program(font, name, is_talk=True, is_glyph=True)

def get_vtt_program(font, name, is_talk=False, is_glyph=False):
    tag = "TSI3" if is_talk else "TSI1"
    if tag not in font:
        raise VTTLibError("%s table not found" % tag)
    try:
        if is_glyph:
            data = font[tag].glyphPrograms[name]
        else:
            data = font[tag].extraPrograms[name]
    except KeyError:
        raise KeyError(
            "%s program missing from %s: '%s'" % (
                "Glyph" if is_glyph else "Extra", tag, name))
    return data.replace("\r", "\n")

AXIS_NAME = {
  '0': "Y",
  '1': "X"
}

REF_POINT = {
  '0': "2",
  '1': "1"
}

def pattern_match_vtttalk(tokens, points, optimize_ipanchor):
  vttalk = []
  axis = "X"
  refPt = {"1": 0, "2": 0}
  IP = 0
  while IP < len(tokens):
    cmd = tokens[IP]
    IP += 1
    mnemonic = cmd[0]
    operands = cmd[1:]
    if mnemonic == "SVTCA":
      axis = AXIS_NAME[operands[0]]

    elif mnemonic == "CALL" and len(operands) == 3 and operands[2] == 114:
      a, b, _ = operands
      vttalk.append('Res{}Anchor({},{})'.format(axis, a, b))
      # side-effect:
      refPt["2"] = a

    elif mnemonic == "CALL" and len(operands) == 3 and (operands[2] == 105 or operands[2] == 106):
      # FIXME: What's the difference between functions 105 and 106 ?
      a, b, _ = operands
      vttalk.append('Res{}Dist({},{})'.format(axis, a, b))
      # side-effect:
      refPt["1"] = a
      refPt["2"] = b

    elif mnemonic == "MDRP" and len(operands)==2 and operands[0] == '01110':
      a = operands[1]
      vttalk.append('{}Dist({},{},>=)'.format(axis, refPt["2"], a))

    elif mnemonic == "IP" and len(operands) == 1:
      pt = operands[0]
      next_cmd = tokens[IP]
      if optimize_ipanchor and next_cmd[0] == "MDAP" and next_cmd[1] == '1' and next_cmd[2] == pt: #'1' == "R"
        keyword = "IPAnchor"
        IP += 1
      else:
        keyword = "Interpolate"

      # the order of the Interpolate params depend on the coordinates of the actual points
      if axis == 'X':
        coord = 0
      else: # if axis == 'Y':
        coord = 1
      if points[refPt["1"]][coord] > points[refPt["2"]][coord]:
        vttalk.append('{}{}({},{},{})'.format(axis, keyword, refPt["1"], pt, refPt["2"]))
      else:
        vttalk.append('{}{}({},{},{})'.format(axis, keyword, refPt["2"], pt, refPt["1"]))

    elif mnemonic == "MDAP" and len(operands) == 2 and operands[0] == '1': #not sure about round='1'("R") in instruction "MDAP[R], 3"
      pt = operands[1]
      vttalk.append('{}Anchor({})'.format(axis, pt))
      # side-effect:
      refPt["1"] = pt

    elif mnemonic == "SHP" and len(operands) == 2:
      refpt_id, pt = operands
      vttalk.append('{}Shift({},{})'.format(axis, refPt[REF_POINT[refpt_id]], pt))

    elif mnemonic == "SRP1" and len(operands) == 1:
      refPt["1"] = operands[0]

    elif mnemonic == "SRP2" and len(operands) == 1:
      refPt["2"] = operands[0]

    elif mnemonic == "IUP" and operands[0] == '0' and tokens[IP][0] == "IUP" and tokens[IP][1] == '1':
        vttalk.append('Smooth()')
        IP += 1

    else:
      vttalk.append('ASM("{} {}")'.format(mnemonic, " ".join(map(str, operands))))

  return "\n".join(vttalk)

def decompile_glyph_bytecode(font, glyph_name, verbose=False, optimize_ipanchor=False):
  data = get_glyph_assembly(font, glyph_name)
  data = data.strip()
  tokens = tokenize(data)
  points = font["glyf"][glyph_name].coordinates
  vtttalk = pattern_match_vtttalk(tokens, points, optimize_ipanchor)
  if verbose:
    print("== {} ==\n{}\n".format(glyph_name, data))
    # print("== TOKENS ==\n{}\n".format("\n".join(map(str, tokens))))
    print("== VTT Talk ==\n{}\n".format(vtttalk))
  return vtttalk

def decompile_instructions(font):
    if "glyf" not in font:
        raise VTTLibError("Missing 'glyf' table; not a TrueType font")

    glyph_order = font.getGlyphOrder()
    glyf_table = font['glyf']
    for glyph_name in glyph_order:
        #if glyph_name == "uniFB49":
            decompile_glyph_bytecode(font, glyph_name, verbose=True)


def vtt_decompile(infile, outfile):
    font = TTFont(infile)

    decompile_instructions(font)
    #font.save(outfile)

if __name__ == "__main__":
  import sys
  if len(sys.argv) != 2:
    sys.exit("usage: {} infile.ttf".format(sys.argv[0]))

  infile = sys.argv[1]
  outfile = sys.argv[1] + ".out"
  vtt_decompile(infile, outfile)
  print ("done")
