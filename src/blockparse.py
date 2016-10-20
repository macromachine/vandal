"""blockparse.py: Parse operation sequences and construct basic blocks"""

import abc
import typing
import traceback
import collections

import cfg
import evm_cfg
import opcodes
import logger

class BlockParser(abc.ABC):
  @abc.abstractmethod
  def __init__(self, raw:object):
    """
    Constructs a new BlockParser for parsing the given raw input object.

    Args:
      raw: parser-specific object containing raw input to be parsed.
    """

    self._raw = raw
    """raw: parser-specific object containing raw input to be parsed."""

    self._ops = []
    """
    List of program operations extracted from the raw input object.
    Indices from this list are used as unique identifiers for program
    operations when constructing BasicBlocks.
    """

  @abc.abstractmethod
  def parse(self) -> typing.Iterable[cfg.BasicBlock]:
    """
    Parses the raw input object and returns an iterable of BasicBlocks.
    """
    self._ops = []


class EVMDasmParser(BlockParser):
  def __init__(self, dasm:typing.Iterable[str]):
    """
    Parses raw EVM disassembly lines and creates corresponding EVMBasicBlocks.
    This does NOT follow jumps or create graph edges - it just parses the
    disassembly and creates the blocks.

    Args:
      dasm: iterable of raw disasm output lines to be parsed by this instance
    """
    super().__init__(dasm)

  def parse(self):
    super().parse()

    # Construct a list of EVMOp objects from the raw input disassembly
    # lines, ignoring the first line of input (which is the bytecode's hex
    # representation when using Ethereum's disasm tool). Any line which does
    # not produce enough tokens to be valid disassembly after being split() is
    # also ignored.
    for i, l in enumerate(self._raw):
      if len(l.split()) == 1:
        logger.warning("Warning (line {}): skipping invalid disassembly:\n   {}"
                    .format(i+1, l.rstrip()))
        continue
      elif len(l.split()) < 1:
        continue

      try:
        self._ops.append(self.evm_op_from_dasm(l))
      except (ValueError, LookupError) as e:
        logger.log(traceback.format_exc())
        logger.warning("Warning (line {}): skipping invalid disassembly:\n   {}"
                    .format(i+1, l.rstrip()))

    return evm_cfg.blocks_from_ops(self._ops)

  @staticmethod
  def evm_op_from_dasm(line:str) -> evm_cfg.EVMOp:
    """
    Creates and returns a new EVMOp object from a raw line of disassembly.

    Args:
      line: raw line of output from Ethereum's disasm disassembler.

    Returns:
      evm_cfg.EVMOp: the constructed EVMOp
    """
    toks = line.replace("=>", " ").split()
    if len(toks) > 2:
      return evm_cfg.EVMOp(int(toks[0]), opcodes.opcode_by_name(toks[1]), int(toks[2], 16))
    elif len(toks) > 1:
      return evm_cfg.EVMOp(int(toks[0]), opcodes.opcode_by_name(toks[1]))
    else:
      raise NotImplementedError("Could not parse unknown disassembly format:" +
                                "\n    {}".format(line))


class EVMBytecodeParser(BlockParser):
  def __init__(self, bytecode:str or bytes):
    super().__init__(bytecode)

    if type(bytecode) is str:
      bytecode = bytes.fromhex(bytecode.replace("0x", ""))
    else:
      bytecode = bytes(bytecode)

    self._raw = bytecode

    # Track the program counter as we traverse the bytecode
    self.__pc = 0

  def __consume(self, n):
    bytes_ = self._raw[self.__pc : self.__pc + n]
    self.__pc += n
    return bytes_

  def __has_more_bytes(self):
    return self.__pc < len(self._raw)

  def parse(self):
    super().parse()

    while self.__has_more_bytes():
      pc = self.__pc
      byte = int.from_bytes(self.__consume(1), "big")
      op = opcodes.opcode_by_value(byte)
      const, const_size = None, 0

      if op.is_push:
        const_size = op.code - opcodes.PUSH1.code + 1

      if const_size > 0:
        const = self.__consume(const_size)
        const = int.from_bytes(const, "big")

      self._ops.append(evm_cfg.EVMOp(pc, op, const))

    return evm_cfg.blocks_from_ops(self._ops)
