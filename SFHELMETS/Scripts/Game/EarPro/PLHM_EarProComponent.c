// Phaseline Helmets - articulated ear protection.
// The ear-pro item keeps a replicated per-side state (deployed / vented / stowed). Cups are moved with bone deltas on the
// item's own skeleton (EP_Arm_*, EP_Cup_*): once at rest (the pose persists, no per-frame cost) and per frame only while
// a transition plays. A transition starts on each machine when the wearer's hand clip starts there (the proxy gadget
// reaches the left hand), so cup and hand stay in step without streaming transforms.
[ComponentEditorProps(category: "Phaseline/Helmets", description: "Articulated helmet ear protection (state, replication, cup motion)")]
class PLHM_EarProComponentClass : ScriptComponentClass
{
}

enum PLHM_EEarProState
{
	DEPLOYED,
	VENTED,
	STOWED
}

enum PLHM_EEarProAction
{
	NONE,
	RAISE,		// deployed -> stowed
	LOWER,		// stowed -> deployed
	VENT,		// deployed -> vented
	UNVENT		// vented -> deployed
}

enum PLHM_EEarProRequest
{
	TOGGLE_STOW = 8,	// stow the given cups, or bring them all down if they are all stowed
	TOGGLE_VENT = 9		// vent the deployed cups, or close the vented ones
}

class PLHM_EarProComponent : ScriptComponent
{
	static const int SIDE_L = 1;
	static const int SIDE_R = 2;

	[Attribute("1", desc: "Mount supports the stowed position (Ops-Core AMP rail mount: yes; Peltor ARC adapter: no)")]
	protected bool m_bCanStow;

	[Attribute("1", desc: "Mount supports the vented position")]
	protected bool m_bCanVent;

	[Attribute("0.171 0.245 0.954", desc: "Right hinge-pin axis, Blender character frame (+X right, +Y forward, +Z up); x mirrored for the left side")]
	protected vector m_vHingeAxis;

	[Attribute("14 0 0", desc: "Vented pose: splay swing spin (deg)")]
	protected vector m_vVentPose;

	[Attribute("24 161.5 -4.5", desc: "Stowed pose: splay swing spin (deg)")]
	protected vector m_vStowPose;

	[Attribute("46.5", desc: "Stowed pose: cup fold (deg)")]
	protected float m_fStowYaw;

	[Attribute("0", desc: "Hand clip set (PLHM_EarProClips): 0 AMP SF/Maritime, 1 AMP XP, 2 ComTac SF/Maritime, 3 ComTac XP, 4 ComTac VI SF/Maritime, 5 ComTac VI XP")]
	protected int m_iClipSet;

	[RplProp(onRplName: "OnRplState")]
	protected int m_iState;			// bits 0-1 left, 2-3 right (PLHM_EEarProState)

	[RplProp(onRplName: "OnRplState")]
	protected int m_iSeq;			// +1 per transition

	[RplProp(onRplName: "OnRplState")]
	protected int m_iTransition;		// clip (PLHM_EarProClips) | (sides that started VENTED << 8)

	// local
	protected ref map<string, ref array<vector>> m_mRest;
	protected int m_iSeenSeq = -1;
	protected bool m_bTicking;
	protected bool m_bPending;
	protected float m_fPendingSince;
	protected float m_fT0;
	protected int m_iAnimClip;
	protected int m_iAnimMask;
	protected int m_iAnimVentSrc;
	protected float m_fBusyUntil;		// server
	protected InventoryItemComponent m_Item;
	protected InventoryItemComponent m_ParentItem;

	//------------------------------------------------------------------------------------------------ state
	static int GetSideState(int packed, int side)
	{
		if (side == SIDE_L)
			return packed & 3;
		return (packed >> 2) & 3;
	}

	int GetState(int side)
	{
		return GetSideState(m_iState, side);
	}

	bool CanVent()
	{
		return m_bCanVent;
	}

	bool CanStow()
	{
		return m_bCanStow;
	}

	int GetClipSet()
	{
		return m_iClipSet;
	}

	static int TargetOf(int action)
	{
		if (action == PLHM_EEarProAction.RAISE)
			return PLHM_EEarProState.STOWED;
		if (action == PLHM_EEarProAction.VENT)
			return PLHM_EEarProState.VENTED;
		return PLHM_EEarProState.DEPLOYED;
	}

	static int SourceOf(int action)
	{
		if (action == PLHM_EEarProAction.LOWER)
			return PLHM_EEarProState.STOWED;
		if (action == PLHM_EEarProAction.UNVENT)
			return PLHM_EEarProState.VENTED;
		return PLHM_EEarProState.DEPLOYED;
	}

	//! is this action valid for every side in the mask right now (server check)
	bool CanDo(int action, int sideMask)
	{
		if (sideMask == 0)
			return false;
		if (action == PLHM_EEarProAction.RAISE && !m_bCanStow)
			return false;
		if ((action == PLHM_EEarProAction.VENT || action == PLHM_EEarProAction.UNVENT) && !m_bCanVent)
			return false;
		foreach (int side : {SIDE_L, SIDE_R})
		{
			if (!(sideMask & side))
				continue;
			int st = GetState(side);
			if (action == PLHM_EEarProAction.RAISE && st == PLHM_EEarProState.STOWED)
				return false;
			if (action != PLHM_EEarProAction.RAISE && st != SourceOf(action))
				return false;
		}
		return true;
	}

	//! toggle requests -> concrete action + the sides it applies to (NONE = nothing to do)
	int ResolveToggle(int request, int sideMask, out int outMask)
	{
		outMask = 0;
		if (request == PLHM_EEarProRequest.TOGGLE_STOW)
		{
			foreach (int side : {SIDE_L, SIDE_R})
			{
				if ((sideMask & side) && GetState(side) != PLHM_EEarProState.STOWED)
					outMask |= side;
			}
			if (outMask != 0)
				return PLHM_EEarProAction.RAISE;
			outMask = sideMask;
			return PLHM_EEarProAction.LOWER;
		}
		if (request == PLHM_EEarProRequest.TOGGLE_VENT)
		{
			foreach (int side1 : {SIDE_L, SIDE_R})
			{
				if ((sideMask & side1) && GetState(side1) == PLHM_EEarProState.DEPLOYED)
					outMask |= side1;
			}
			if (outMask != 0)
				return PLHM_EEarProAction.VENT;
			foreach (int side2 : {SIDE_L, SIDE_R})
			{
				if ((sideMask & side2) && GetState(side2) == PLHM_EEarProState.VENTED)
					outMask |= side2;
			}
			if (outMask != 0)
				return PLHM_EEarProAction.UNVENT;
			return PLHM_EEarProAction.NONE;
		}
		outMask = sideMask;
		return request;
	}

	bool IsBusy()
	{
		return GetGame().GetWorld().GetWorldTime() * 0.001 < m_fBusyUntil;
	}

	//! server: start a clip (state flips now; every machine plays the cup motion with the wearer's hand clip)
	void Server_BeginTransition(int clip, float lead = 0)
	{
		int action = PLHM_EarProClips.ActionOf(clip);
		int sideMask = PLHM_EarProClips.MaskOf(clip);
		int target = TargetOf(action);
		int ventSrc = 0;
		int st = m_iState;
		foreach (int side : {SIDE_L, SIDE_R})
		{
			if (!(sideMask & side))
				continue;
			if (GetState(side) == PLHM_EEarProState.VENTED)
				ventSrc |= side;
			if (side == SIDE_L)
				st = (st & ~3) | target;
			else
				st = (st & ~12) | (target << 2);
		}
		m_iState = st;
		m_iSeq++;
		m_iTransition = clip | (ventSrc << 8);
		m_fBusyUntil = GetGame().GetWorld().GetWorldTime() * 0.001 + lead + PLHM_EarProClips.Duration(clip);
		Replication.BumpMe();
		OnRplState();
	}

	//------------------------------------------------------------------------------------------------ timelines
	static float Ease(float x)
	{
		x = Math.Clamp(x, 0, 1);
		return x * x * (3 - 2 * x);
	}

	static float KeyValue(array<float> k, float t)
	{
		if (t <= k[0])
			return k[1];
		for (int i = 0; i + 3 < k.Count(); i += 2)
		{
			if (t <= k[i + 2])
				return k[i + 1] + (k[i + 3] - k[i + 1]) * Ease((t - k[i]) / Math.Max(0.000001, k[i + 2] - k[i]));
		}
		return k[k.Count() - 1];
	}

	//------------------------------------------------------------------------------------------------ lifecycle
	override void OnPostInit(IEntity owner)
	{
		m_Item = InventoryItemComponent.Cast(owner.FindComponent(InventoryItemComponent));
		if (m_Item)
			m_Item.m_OnParentSlotChangedInvoker.Insert(OnParentSlotChanged);
		if (!System.IsConsoleApp())
			GetGame().GetCallqueue().CallLater(OnRplState, 250, false);
	}

	override void OnDelete(IEntity owner)
	{
		GetGame().GetCallqueue().Remove(Tick);
		GetGame().GetCallqueue().Remove(OnRplState);
		GetGame().GetCallqueue().Remove(ApplyState);
		if (m_Item)
			m_Item.m_OnParentSlotChangedInvoker.Remove(OnParentSlotChanged);
		if (m_ParentItem)
			m_ParentItem.m_OnParentSlotChangedInvoker.Remove(OnParentSlotChanged);
	}

	protected void OnParentSlotChanged(InventoryStorageSlot oldSlot, InventoryStorageSlot newSlot)
	{
		if (System.IsConsoleApp())
			return;
		// the worn visual is (re)created by the loadout after the slot change: rebind and re-pose shortly after
		m_mRest = null;
		WatchParentItem();
		GetGame().GetCallqueue().Remove(ApplyState);
		GetGame().GetCallqueue().CallLater(ApplyState, 200, false);
	}

	//! the helmet carrying the ear-pro can be unequipped / re-equipped without the ear-pro's own slot changing
	protected void WatchParentItem()
	{
		if (m_ParentItem)
			m_ParentItem.m_OnParentSlotChangedInvoker.Remove(OnParentSlotChanged);
		m_ParentItem = null;
		IEntity p = GetOwner().GetParent();
		if (p && !ChimeraCharacter.Cast(p))
		{
			m_ParentItem = InventoryItemComponent.Cast(p.FindComponent(InventoryItemComponent));
			if (m_ParentItem)
				m_ParentItem.m_OnParentSlotChangedInvoker.Insert(OnParentSlotChanged);
		}
	}

	protected void OnRplState()
	{
		if (System.IsConsoleApp())
		{
			m_iSeenSeq = m_iSeq;
			return;
		}
		if (m_iSeenSeq == -1 || !GetWearer())
		{
			// first sight (spawn, join in progress) or not worn: show the state, no motion
			m_iSeenSeq = m_iSeq;
			ApplyState();
			return;
		}
		if (m_iSeq != m_iSeenSeq)
		{
			m_iSeenSeq = m_iSeq;
			m_iAnimClip = m_iTransition & 255;
			m_iAnimMask = PLHM_EarProClips.MaskOf(m_iAnimClip);
			m_iAnimVentSrc = (m_iTransition >> 8) & 3;
			m_bPending = true;
			m_fPendingSince = Now();
			StartTicking();
			return;
		}
		ApplyState();
	}

	protected float Now()
	{
		return GetGame().GetWorld().GetWorldTime() * 0.001;
	}

	ChimeraCharacter GetWearer()
	{
		IEntity root = GetOwner().GetRootParent();
		if (root == GetOwner())
			return null;
		return ChimeraCharacter.Cast(root);
	}

	//------------------------------------------------------------------------------------------------ motion
	protected void StartTicking()
	{
		if (m_bTicking)
			return;
		m_bTicking = true;
		// worn items are not ACTIVE on network clients (no EOnFrame there): tick on the call queue
		GetGame().GetCallqueue().CallLater(Tick, 0, true);
	}

	protected void StopTicking()
	{
		m_bTicking = false;
		GetGame().GetCallqueue().Remove(Tick);
	}

	protected bool HandHasProxy()
	{
		ChimeraCharacter ch = GetWearer();
		if (!ch || !ch.GetCharacterController())
			return false;
		IEntity g = ch.GetCharacterController().GetAttachedGadgetAtLeftHandSlot();
		return g && g.FindComponent(PLHM_EarProHandComponent);
	}

	protected void Tick()
	{
		float now = Now();
		if (m_bPending)
		{
			// start with the wearer's hand clip on THIS machine (the owner may sling a weapon first; fallback 3 s)
			if (!HandHasProxy() && now - m_fPendingSince < 3.0)
				return;
			m_bPending = false;
			m_fT0 = now;
		}
		float t = now - m_fT0;
		if (t >= PLHM_EarProClips.Duration(m_iAnimClip) || !BindModel())
		{
			StopTicking();
			ApplyState();
			return;
		}
		foreach (int side : {SIDE_L, SIDE_R})
		{
			if (!(m_iAnimMask & side))
				continue;
			array<float> ks, kw, kn, ky;
			if (!PLHM_EarProClips.Keys(m_iAnimClip, side, ks, kw, kn, ky))
				continue;
			if ((m_iAnimVentSrc & side) && ks.Count() > 1)
				ks[1] = m_vVentPose[0];		// stowing from the vented position: start the pull-out from there
			int s = 1;
			if (side == SIDE_L)
				s = -1;
			PoseSide(s, KeyValue(ks, t), KeyValue(kw, t), KeyValue(kn, t), KeyValue(ky, t));
		}
	}

	//! pose both sides for the replicated state (once; the pose persists)
	void ApplyState()
	{
		if (System.IsConsoleApp() || m_bTicking || !BindModel())
			return;
		ApplySideState(-1, GetState(SIDE_L));
		ApplySideState(1, GetState(SIDE_R));
	}

	protected void ApplySideState(int s, int state)
	{
		if (state == PLHM_EEarProState.STOWED)
			PoseSide(s, m_vStowPose[0], m_vStowPose[1], m_vStowPose[2], m_fStowYaw);
		else if (state == PLHM_EEarProState.VENTED)
			PoseSide(s, m_vVentPose[0], m_vVentPose[1], m_vVentPose[2], 0);
		else
			PoseSide(s, 0, 0, 0, 0);
	}

	//------------------------------------------------------------------------------------------------ skeleton
	//! Clothing gives the worn item a visual driven by the character skeleton (VCFlags.INHERIT_PARENT_SKELETON); bone
	//! deltas do not reach it. Recreate the same mesh as an independent instance (same workaround as Phaseline NVG Systems).
	protected bool EnsureIndependentVisual(IEntity entity)
	{
		if (!entity || !entity.GetVObject())
			return false;
		if ((entity.SetVComponentFlags(0) & VCFlags.INHERIT_PARENT_SKELETON) == 0)
			return false;
		Resource mesh = Resource.Load(entity.GetVObject().GetResourceName());
		if (!mesh || !mesh.IsValid())
			return false;
		entity.SetObject(null, "");
		entity.SetObject(mesh.GetResource().ToVObject(), "");
		return true;
	}

	protected bool BindModel()
	{
		IEntity owner = GetOwner();
		if (!GetWearer())
			return false;
		if (EnsureIndependentVisual(owner))
			m_mRest = null;
		Animation anim = owner.GetAnimation();
		if (!anim || anim.GetBoneIndex("EP_Cup_L") == -1)
			return false;
		owner.SetFlags(EntityFlags.ACTIVE);
		if (m_mRest)
			return true;
		// capture the bind matrices from a clean (identity delta) pose
		m_mRest = new map<string, ref array<vector>>();
		vector id[4];
		Math3D.MatrixIdentity4(id);
		foreach (string b : {"EP_Arm_L", "EP_Cup_L", "EP_Arm_R", "EP_Cup_R"})
		{
			int bi = anim.GetBoneIndex(b);
			if (bi == -1)
				continue;
			anim.SetBoneMatrix(owner, bi, id);
		}
		foreach (string b2 : {"EP_Arm_L", "EP_Cup_L", "EP_Arm_R", "EP_Cup_R"})
		{
			int bj = anim.GetBoneIndex(b2);
			if (bj == -1)
				continue;
			vector m[4];
			anim.GetBoneMatrix(bj, m);
			array<vector> a = {m[0], m[1], m[2], m[3]};
			m_mRest.Insert(b2, a);
		}
		return true;
	}

	//! Rodrigues rotation; columns in m[0..2]
	static void RotAxis(vector a, float th, out vector m[4])
	{
		a.Normalize();
		float c = Math.Cos(th);
		float s = Math.Sin(th);
		for (int i = 0; i < 3; i++)
		{
			vector e = vector.Zero;
			e[i] = 1;
			m[i] = e * c + (a * e) * s + a * (vector.Dot(a, e) * (1 - c));
		}
		m[3] = vector.Zero;
	}

	static void Mul(vector A[4], vector B[4], out vector C[4])
	{
		vector a0 = A[0];
		vector a1 = A[1];
		vector a2 = A[2];
		for (int j = 0; j < 3; j++)
		{
			vector bj = B[j];
			C[j] = a0 * bj[0] + a1 * bj[1] + a2 * bj[2];
		}
		C[3] = vector.Zero;
	}

	//! D = R^T * X * R (rotation X about the bone origin, expressed as a bone-local delta)
	static void Conj(vector R[4], vector X[4], out vector D[4])
	{
		vector a0 = R[0];
		vector a1 = R[1];
		vector a2 = R[2];
		vector rt[4];
		for (int j = 0; j < 3; j++)
			rt[j] = Vector(a0[j], a1[j], a2[j]);
		rt[3] = vector.Zero;
		vector t1[4];
		Mul(rt, X, t1);
		Mul(t1, R, D);
	}

	//! Blender character-frame direction -> item model space (Head pivot, Enfusion axes)
	static vector MapDir(vector bl)
	{
		return Vector(-bl[0], bl[2], -bl[1]);
	}

	//! s = -1 left, +1 right; mechanism: arm = swing(lateral) o splay(hinge pin) about the shoe pivot,
	//! cup = arm o fold(vertical) o spin(cup normal) about the gimbal (OUTLAWHELMETS/_earpro/blender/ep_mech.py)
	protected void PoseSide(int s, float splay, float swing, float spin, float yaw)
	{
		IEntity owner = GetOwner();
		Animation anim = owner.GetAnimation();
		string sd = "R";
		if (s < 0)
			sd = "L";
		int ia = anim.GetBoneIndex("EP_Arm_" + sd);
		int ic = anim.GetBoneIndex("EP_Cup_" + sd);
		array<vector> ra = m_mRest.Get("EP_Arm_" + sd);
		array<vector> rc = m_mRest.Get("EP_Cup_" + sd);
		if (ia == -1 || ic == -1 || !ra || !rc)
			return;
		vector Ra[4], Rc[4];
		for (int i = 0; i < 3; i++)
		{
			Ra[i] = ra[i];
			Rc[i] = rc[i];
		}
		Ra[3] = vector.Zero;
		Rc[3] = vector.Zero;
		vector hinge = Vector(m_vHingeAxis[0] * s, m_vHingeAxis[1], m_vHingeAxis[2]);
		vector rsw[4], rsp[4], rarm[4], ryw[4], rsn[4], rg[4], da[4], dc[4];
		RotAxis(MapDir("1 0 0"), -swing * Math.DEG2RAD, rsw);
		RotAxis(MapDir(hinge), s * splay * Math.DEG2RAD, rsp);
		Mul(rsw, rsp, rarm);
		RotAxis(MapDir("0 0 1"), -s * yaw * Math.DEG2RAD, ryw);
		RotAxis(MapDir(Vector(s, 0, 0)), -spin * Math.DEG2RAD, rsn);
		Mul(ryw, rsn, rg);
		Conj(Ra, rarm, da);
		Conj(Rc, rg, dc);
		anim.SetBoneMatrix(owner, ia, da);
		anim.SetBoneMatrix(owner, ic, dc);
	}
}
