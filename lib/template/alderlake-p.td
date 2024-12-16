//===- X86SchedAlderlakeP.td - X86 Alderlake-P Scheduling ----*- tablegen -*-=//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// This file defines the machine model for Alderlake-P core to support
// instruction scheduling and other instruction cost heuristics.
//
//===----------------------------------------------------------------------===//

def AlderlakePModel : SchedMachineModel {
  // Alderlake-P core can allocate 6 uops per cycle.
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

let SchedModel = AlderlakePModel in {

// Alderlake-P core can issue micro-ops to 12 different ports in one cycle.
def ADLPPort00 : ProcResource<1>;
def ADLPPort01 : ProcResource<1>;
def ADLPPort02 : ProcResource<1>;
def ADLPPort03 : ProcResource<1>;
def ADLPPort04 : ProcResource<1>;
def ADLPPort05 : ProcResource<1>;
def ADLPPort06 : ProcResource<1>;
def ADLPPort07 : ProcResource<1>;
def ADLPPort08 : ProcResource<1>;
def ADLPPort09 : ProcResource<1>;
def ADLPPort10 : ProcResource<1>;
def ADLPPort11 : ProcResource<1>;

// Workaround to represent invalid ports. WriteRes shouldn't use this resource.
def ADLPPortInvalid : ProcResource<1>;

// Many micro-ops are capable of issuing on multiple ports.
def ADLPPort00_01          : ProcResGroup<[ADLPPort00, ADLPPort01]>;
def ADLPPort00_01_05       : ProcResGroup<[ADLPPort00, ADLPPort01, ADLPPort05]>;
def ADLPPort00_01_05_06    : ProcResGroup<[ADLPPort00, ADLPPort01, ADLPPort05, ADLPPort06]>;
def ADLPPort00_05          : ProcResGroup<[ADLPPort00, ADLPPort05]>;
def ADLPPort00_05_06       : ProcResGroup<[ADLPPort00, ADLPPort05, ADLPPort06]>;
def ADLPPort00_06          : ProcResGroup<[ADLPPort00, ADLPPort06]>;
def ADLPPort01_05          : ProcResGroup<[ADLPPort01, ADLPPort05]>;
def ADLPPort01_05_10       : ProcResGroup<[ADLPPort01, ADLPPort05, ADLPPort10]>;
def ADLPPort02_03          : ProcResGroup<[ADLPPort02, ADLPPort03]>;
def ADLPPort02_03_11       : ProcResGroup<[ADLPPort02, ADLPPort03, ADLPPort11]>;
def ADLPPort07_08          : ProcResGroup<[ADLPPort07, ADLPPort08]>;

// EU has 112 reservation stations.
def ADLPPort00_01_05_06_10 : ProcResGroup<[ADLPPort00, ADLPPort01, ADLPPort05,
                                           ADLPPort06, ADLPPort10]> {
  let BufferSize = 112;
}

// STD has 48 reservation stations.
def ADLPPort04_09          : ProcResGroup<[ADLPPort04, ADLPPort09]> {
  let BufferSize = 48;
}

// MEM has 72 reservation stations.
def ADLPPort02_03_07_08_11 : ProcResGroup<[ADLPPort02, ADLPPort03, ADLPPort07,
                                           ADLPPort08, ADLPPort11]> {
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
multiclass ADLPWriteResPair<X86FoldableSchedWrite SchedRW,
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
  def : WriteRes<SchedRW.Folded, !listconcat([ADLPPort02_03_11], ExePorts)> {
    let Latency = !add(Lat, LoadLat);
    let ResourceCycles = !listconcat([1], Res);
    let NumMicroOps = !add(UOps, LoadUOps);
  }
}
