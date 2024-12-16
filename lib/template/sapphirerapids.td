//=- X86SchedSapphireRapids.td - X86 SapphireRapids Scheduling *- tablegen -*=//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file defines the machine model for SapphireRapids to support instruction
// scheduling and other instruction cost heuristics.
//
//===----------------------------------------------------------------------===//

def SapphireRapidsModel : SchedMachineModel {
  // SapphireRapids can allocate 6 uops per cycle.
  let IssueWidth = 6; // Based on allocator width.
  let MicroOpBufferSize = 512; // Based on the reorder buffer.
  let LoadLatency = 5;
  let MispredictPenalty = 14;

  // Latency for microcoded instructions or instructions without latency info.
  int MaxLatency = 100;

  // Based on the LSD (loop-stream detector) queue size (ST).
  let LoopMicroOpBufferSize = 72;

  // This flag is set to allow the scheduler to assign a default model to
  // unrecognized opcodes.
  let CompleteModel = 0;
}

let SchedModel = SapphireRapidsModel in {

// SapphireRapids can issue micro-ops to 12 different ports in one cycle.
def SPRPort00 : ProcResource<1>;
def SPRPort01 : ProcResource<1>;
def SPRPort02 : ProcResource<1>;
def SPRPort03 : ProcResource<1>;
def SPRPort04 : ProcResource<1>;
def SPRPort05 : ProcResource<1>;
def SPRPort06 : ProcResource<1>;
def SPRPort07 : ProcResource<1>;
def SPRPort08 : ProcResource<1>;
def SPRPort09 : ProcResource<1>;
def SPRPort10 : ProcResource<1>;
def SPRPort11 : ProcResource<1>;

// Workaround to represent invalid ports. WriteRes shouldn't use this resource.
def SPRPortInvalid :ProcResource<1>;

// Many micro-ops are capable of issuing on multiple ports.
def SPRPort00_01          : ProcResGroup<[SPRPort00, SPRPort01]>;
def SPRPort00_01_05       : ProcResGroup<[SPRPort00, SPRPort01, SPRPort05]>;
def SPRPort00_01_05_06    : ProcResGroup<[SPRPort00, SPRPort01, SPRPort05, SPRPort06]>;
def SPRPort00_05          : ProcResGroup<[SPRPort00, SPRPort05]>;
def SPRPort00_05_06       : ProcResGroup<[SPRPort00, SPRPort05, SPRPort06]>;
def SPRPort00_06          : ProcResGroup<[SPRPort00, SPRPort06]>;
def SPRPort01_05          : ProcResGroup<[SPRPort01, SPRPort05]>;
def SPRPort01_05_10       : ProcResGroup<[SPRPort01, SPRPort05, SPRPort10]>;
def SPRPort02_03          : ProcResGroup<[SPRPort02, SPRPort03]>;
def SPRPort02_03_11       : ProcResGroup<[SPRPort02, SPRPort03, SPRPort11]>;
def SPRPort07_08          : ProcResGroup<[SPRPort07, SPRPort08]>;

// EU has 112 reservation stations.
def SPRPort00_01_05_06_10 : ProcResGroup<[SPRPort00, SPRPort01, SPRPort05,
                                          SPRPort06, SPRPort10]> {
  let BufferSize = 112;
}

// STD has 48 reservation stations.
def SPRPort04_09          : ProcResGroup<[SPRPort04, SPRPort09]> {
  let BufferSize = 48;
}

// MEM has 72 reservation stations.
def SPRPort02_03_07_08_11 : ProcResGroup<[SPRPort02, SPRPort03, SPRPort07,
                                          SPRPort08, SPRPort11]> {
  let BufferSize = 72;
}

// Integer loads are 5 cycles, so ReadAfterLd registers needn't be available
// until 5 cycles after the memory operand.
def : ReadAdvance<ReadAfterLd, 5>;

// Vector loads are 6 cycles, so ReadAfterVec*Ld registers needn't be available
// until 6 cycles after the memory operand.
def : ReadAdvance<ReadAfterVecLd, 6>;
def : ReadAdvance<ReadAfterVecXLd, 6>;
def : ReadAdvance<ReadAfterVecYLd, 6>;

def : ReadAdvance<ReadInt2Fpu, 0>;

// Many SchedWrites are defined in pairs with and without a folded load.
// Instructions with folded loads are usually micro-fused, so they only appear
// as two micro-ops when queued in the reservation station.
// This multiclass defines the resource usage for variants with and without
// folded loads.
multiclass SPRWriteResPair<X86FoldableSchedWrite SchedRW,
                           list<ProcResourceKind> ExePorts,
                           int Lat, list<int> Res = [1], int UOps = 1,
                           int LoadLat = 5, int LoadUOps = 1> {
  // Register variant is using a single cycle on ExePort.
  def : WriteRes<SchedRW, ExePorts> {
    let Latency = Lat;
    let ResourceCycles = Res;
    let NumMicroOps = UOps;
  }

  // Memory variant also uses a cycle on port 2/3/11 and adds LoadLat cycles to
  // the latency (default = 5).
  def : WriteRes<SchedRW.Folded, !listconcat([SPRPort02_03_11], ExePorts)> {
    let Latency = !add(Lat, LoadLat);
    let ResourceCycles = !listconcat([1], Res);
    let NumMicroOps = !add(UOps, LoadUOps);
  }
}
