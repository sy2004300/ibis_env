****************
.protect
.lib '{{MODEL_ROOT}}/spectre/rbd.lib' rbd_t
.lib '{{MODEL_ROOT}}/spectre/cap.lib' cap_t
.lib '{{MODEL_ROOT}}/spectre/mos_var.lib' mos_var_tt
.inc '{{SPF_ROOT}}/demo_phy_io_diff.typical.spf'
.unprotect

.option method=gear
.option runlvl=5

*** T2B-controlled pins (local sources disabled) ***
*vvddq vddq 0 dc vddq_typ
*vvss vss 0 dc 0
*vtxoe txoe 0 dc 0
*vtxdat txdat 0 dc 0

*** active local power ***
vvdd VDD 0 dc vdd_typ

*** target impedance: 30ohm; minimum valid code = 4'b1111 ***
vreg_txslice_pd3 reg_txslice_pd[3] 0 dc vdd_typ
vreg_txslice_pd2 reg_txslice_pd[2] 0 dc vdd_typ
vreg_txslice_pd1 reg_txslice_pd[1] 0 dc vdd_typ
vreg_txslice_pd0 reg_txslice_pd[0] 0 dc vdd_typ

vreg_txslice_pu3 reg_txslice_pu[3] 0 dc vdd_typ
vreg_txslice_pu2 reg_txslice_pu[2] 0 dc vdd_typ
vreg_txslice_pu1 reg_txslice_pu[1] 0 dc vdd_typ
vreg_txslice_pu0 reg_txslice_pu[0] 0 dc vdd_typ

*** calibration = 8'h34 ***
vtxzqcal_pd7 txzqcal_pd[7] 0 dc 0
vtxzqcal_pd6 txzqcal_pd[6] 0 dc 0
vtxzqcal_pd5 txzqcal_pd[5] 0 dc vdd_typ
vtxzqcal_pd4 txzqcal_pd[4] 0 dc vdd_typ
vtxzqcal_pd3 txzqcal_pd[3] 0 dc 0
vtxzqcal_pd2 txzqcal_pd[2] 0 dc vdd_typ
vtxzqcal_pd1 txzqcal_pd[1] 0 dc 0
vtxzqcal_pd0 txzqcal_pd[0] 0 dc 0

vtxzqcal_pu7 txzqcal_pu[7] 0 dc 0
vtxzqcal_pu6 txzqcal_pu[6] 0 dc 0
vtxzqcal_pu5 txzqcal_pu[5] 0 dc vdd_typ
vtxzqcal_pu4 txzqcal_pu[4] 0 dc vdd_typ
vtxzqcal_pu3 txzqcal_pu[3] 0 dc 0
vtxzqcal_pu2 txzqcal_pu[2] 0 dc vdd_typ
vtxzqcal_pu1 txzqcal_pu[1] 0 dc 0
vtxzqcal_pu0 txzqcal_pu[0] 0 dc 0

*** MSI default reg_txffe[3:0] = 4'b0000 ***
vreg_txffe3 reg_txffe[3] 0 dc 0
vreg_txffe2 reg_txffe[2] 0 dc 0
vreg_txffe1 reg_txffe[1] 0 dc 0
vreg_txffe0 reg_txffe[0] 0 dc 0
