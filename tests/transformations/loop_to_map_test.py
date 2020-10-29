import argparse
import dace
import numpy as np
from dace.transformation.interstate import LoopToMap

def make_sdfg(with_wcr, map_in_guard):

    sdfg = dace.SDFG(f"loop_to_map_test_{with_wcr}_{map_in_guard}")

    init = sdfg.add_state("init")
    guard = sdfg.add_state("guard")
    body = sdfg.add_state("body")
    after = sdfg.add_state("after")

    N = dace.symbol("N", dace.uint64)

    sdfg.add_edge(init, guard, dace.InterstateEdge(assignments={"i": "0"}))
    sdfg.add_edge(guard, body, dace.InterstateEdge(condition="i < N"))
    sdfg.add_edge(guard, after, dace.InterstateEdge(condition="i >= N"))
    sdfg.add_edge(body, guard, dace.InterstateEdge(assignments={"i": "i + 1"}))

    sdfg.add_array("A", [N], dace.float64)
    sdfg.add_array("B", [N], dace.float64)
    sdfg.add_array("C", [N], dace.float64)
    sdfg.add_array("D", [N], dace.float64)

    a = body.add_read("A")
    b = body.add_read("B")
    c = body.add_write("C")
    d = body.add_write("D")

    if map_in_guard:
        guard_read = guard.add_read("C")
        guard_write = guard.add_write("C")
        guard.add_mapped_tasklet("write_self", {"i": "0:N"},
                                 {"c_in": dace.Memlet("C[i]")},
                                 "c_out = c_in",
                                 {"c_out": dace.Memlet("C[i]")},
                                 external_edges=True,
                                 input_nodes={"C": guard_read},
                                 output_nodes={"C": guard_write})

    tasklet0 = body.add_tasklet("tasklet0", {"a"}, {"c"}, "c = 1/a")
    tasklet1 = body.add_tasklet("tasklet1", {"a", "b"}, {"d"},
                                "d = sqrt(a**2 + b**2)")

    body.add_memlet_path(a, tasklet0, dst_conn="a", memlet=dace.Memlet("A[i]"))
    body.add_memlet_path(
        tasklet0,
        c,
        src_conn="c",
        memlet=dace.Memlet(
            "C[i]", wcr="lambda a, b: a + b" if with_wcr else None))

    body.add_memlet_path(a, tasklet1, dst_conn="a", memlet=dace.Memlet("A[i]"))
    body.add_memlet_path(b, tasklet1, dst_conn="b", memlet=dace.Memlet("B[i]"))
    body.add_memlet_path(
        tasklet1,
        d,
        src_conn="d",
        memlet=dace.Memlet(
            "D[i]", wcr="lambda a, b: a + b" if with_wcr else None))

    return sdfg


def apply_and_verify(sdfg):

    a = 4 * np.ones((args.N, ), dtype=np.float64)
    b = 3 * np.ones((args.N, ), dtype=np.float64)
    c = np.zeros((args.N, ), dtype=np.float64)
    d = np.zeros((args.N, ), dtype=np.float64)

    sdfg.save("derp.sdfg")

    num_transformations = sdfg.apply_transformations(LoopToMap)

    sdfg(A=a, B=b, C=c, D=d, N=args.N)

    if not all(c[:] == 0.25) or not all(d[:] == 5):
        print(c)
        print(d)
        raise ValueError("Validation failed.")

    return num_transformations


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--N", default=64, type=int)
    args = parser.parse_args()

    # Case 0: no wcr, no dataflow in guard. Transformation should apply
    if apply_and_verify(make_sdfg(False, False)) != 1:
        raise RuntimeError("LoopToMap was not applied.")

    # Case 1: wcr is present. Transformation should not apply
    if apply_and_verify(make_sdfg(True, False)) != 0:
        raise RuntimeError("LoopToMap should not have been applied.")

    # Case 2: there is dataflow on the guard state
    if apply_and_verify(make_sdfg(False, True)) != 0:
        raise RuntimeError("LoopToMap should not have been applied.")
