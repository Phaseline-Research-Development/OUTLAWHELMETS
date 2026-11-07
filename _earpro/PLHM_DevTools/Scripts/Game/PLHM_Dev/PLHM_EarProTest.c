// PLHM_DevTools -- Phaseline ear-pro test harness (test worlds only; never shipped).
//
// -plhmMode bones : two mannequins, SF V2 helmet + AMP INH (normal Earpro slot, InheritParentSkeleton) and the test
//                   helmet + AMP OWN (PivotID "Head" slot). Logs bone matrices, poses the EP_* bones ONCE and shoots.
// Log lines [PLHM]...; shots $profile:plhmshots/NNNN_<scene>_<view>.bmp; ends with [PLHM] DONE.
class PLHM_TestCameraClass : CameraBaseClass
{
}

class PLHM_TestCamera : CameraBase
{
}

[EntityEditorProps(category: "PLHM/Debug", description: "Phaseline ear-pro test harness. Test worlds only.")]
class PLHM_EarProTestEntityClass : GenericEntityClass
{
}

class PLHM_EarProTestEntity : GenericEntity
{
	static const ResourceName MANNEQUIN = "{26A9756790131354}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Rifleman.et";
	static const ResourceName SF_HELMET = "{AF457DB4423C4107}Prefabs/Helmets/SF V2 Helmets/SF_Helmet_AOR1 (base dont touch).et";
	static const ResourceName TEST_HELMET = "{09A8CC48C9854619}Prefabs/PLHM_Test/PLHM_SF_TestHelmet.et";
	static const ResourceName AMP_INH = "{9D38E3F126414652}Prefabs/PLHM_Test/PLHM_AMP_Inh.et";
	static const ResourceName AMP_OWN = "{0E8C1AB2350ACB3F}Prefabs/PLHM_Test/PLHM_AMP_Own.et";

	protected string m_sMode = "bones";
	protected int m_iFrame;
	protected int m_iStep;
	protected float m_fNext;
	protected int m_iWaitFrame;
	protected int m_iSnap;
	protected CameraBase m_Camera;
	protected ref array<IEntity> m_aMen = {};
	protected ref array<IEntity> m_aEar = {};
	protected ref array<bool> m_aOwn = {};
	// shot queue
	protected ref array<IEntity> m_aQEnt = {};
	protected ref array<string> m_aQView = {};
	protected ref array<string> m_aQScene = {};
	protected int m_iCamSince = -1;

	[Attribute("", desc: "Mode when no -plhmMode is given (e.g. mpdemo for the Workbench play world)")]
	protected string m_sDefaultMode;

	void PLHM_EarProTestEntity(IEntitySource src, IEntity parent)
	{
		SetEventMask(EntityEvent.FRAME);
		string v;
		if (src)
			src.Get("m_sDefaultMode", v);
		if (v != "")
			m_sMode = v;
		string cli;
		if (System.GetCLIParam("plhmMode", cli) && cli != "")
			m_sMode = cli;
	}

	protected void Log(string s)
	{
		Print("[PLHM] " + s);
	}

	protected float Now()
	{
		return GetWorld().GetWorldTime() * 0.001;
	}

	//------------------------------------------------------------------------------------------------ spawning
	protected IEntity Spawn(ResourceName r, vector p, float yaw = 0)
	{
		Resource res = Resource.Load(r);
		if (!res || !res.IsValid())
		{
			Log("[ERR] cannot load " + r);
			return null;
		}
		EntitySpawnParams sp();
		sp.TransformMode = ETransformMode.WORLD;
		Math3D.AnglesToMatrix(Vector(yaw, 0, 0), sp.Transform);
		sp.Transform[3] = p;
		return GetGame().SpawnEntityPrefab(res, GetWorld(), sp);
	}

	protected string AreaOf(IEntity e)
	{
		BaseLoadoutClothComponent cl = BaseLoadoutClothComponent.Cast(e.FindComponent(BaseLoadoutClothComponent));
		if (cl && cl.GetAreaType())
			return cl.GetAreaType().ClassName();
		return "-";
	}

	protected IEntity FindArea(IEntity c, string area)
	{
		SCR_CharacterInventoryStorageComponent cs = SCR_CharacterInventoryStorageComponent.Cast(c.FindComponent(SCR_CharacterInventoryStorageComponent));
		for (int i = 0; cs && i < cs.GetSlotsCount(); i++)
		{
			InventoryStorageSlot s = cs.GetSlot(i);
			if (s && s.GetAttachedEntity() && AreaOf(s.GetAttachedEntity()) == area)
				return s.GetAttachedEntity();
		}
		return null;
	}

	protected bool Wear(IEntity c, ResourceName item)
	{
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(c.FindComponent(SCR_InventoryStorageManagerComponent));
		SCR_CharacterInventoryStorageComponent cs = SCR_CharacterInventoryStorageComponent.Cast(c.FindComponent(SCR_CharacterInventoryStorageComponent));
		IEntity old = FindArea(c, "LoadoutHeadCoverArea");
		if (old)
			inv.TryDeleteItem(old);
		IEntity e = Spawn(item, c.GetOrigin() + "0 3 0");
		return e && inv.EquipAny(cs, e);
	}

	protected IEntity Helmet(IEntity c)
	{
		return FindArea(c, "LoadoutHeadCoverArea");
	}

	protected IEntity InsertIntoHelmet(IEntity c, ResourceName item)
	{
		IEntity helmet = Helmet(c);
		if (!helmet)
		{
			Log("[ERR] no helmet on " + c.ToString());
			return null;
		}
		BaseInventoryStorageComponent st = BaseInventoryStorageComponent.Cast(helmet.FindComponent(ClothNodeStorageComponent));
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(c.FindComponent(SCR_InventoryStorageManagerComponent));
		IEntity e = Spawn(item, c.GetOrigin() + "0 3 0");
		bool ok = e && st && inv.TryInsertItemInStorage(e, st, -1);
		Log(string.Format("insert %1 into %2 -> %3", item, helmet.GetPrefabData().GetPrefabName(), ok));
		return e;
	}

	protected vector BoneWorld(IEntity c, string bone)
	{
		Animation anim = c.GetAnimation();
		int bi = anim.GetBoneIndex(bone);
		vector bm[4];
		anim.GetBoneMatrix(bi, bm);
		return c.CoordToParent(bm[3]);
	}

	//------------------------------------------------------------------------------------------------ matrix helpers
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

	//! C = A*B (columns stored in m[0..2])
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

	static void Tr(vector A[4], out vector T[4])
	{
		vector a0 = A[0];
		vector a1 = A[1];
		vector a2 = A[2];
		for (int j = 0; j < 3; j++)
			T[j] = Vector(a0[j], a1[j], a2[j]);
		T[3] = vector.Zero;
	}

	//! D = R^T * X * R
	static void Conj(vector R[4], vector X[4], out vector D[4])
	{
		vector rt[4], t1[4];
		Tr(R, rt);
		Mul(rt, X, t1);
		Mul(t1, R, D);
	}

	string M2S(vector m[4])
	{
		return string.Format("x%1 y%2 z%3 p%4", m[0], m[1], m[2], m[3]);
	}

	//! Blender character-frame direction -> item model space (OWN = Head-pivot frame, INH = character model frame)
	vector MapDir(vector bl, bool own)
	{
		if (own)
			return Vector(-bl[0], bl[2], -bl[1]);
		return Vector(bl[0], bl[2], bl[1]);
	}

	//! pose one ear-pro: Blender joint values per side (deg); s = -1 left, +1 right
	void PoseSide(IEntity ear, bool own, int s, float splay, float swing, float spin, float yaw, map<string, ref array<vector> > rest)
	{
		Animation anim = ear.GetAnimation();
		string sd = "R";
		if (s < 0)
			sd = "L";
		int ia = anim.GetBoneIndex("EP_Arm_" + sd);
		int ic = anim.GetBoneIndex("EP_Cup_" + sd);
		if (ia == -1 || ic == -1)
		{
			Log("[ERR] EP bones missing on " + ear.ToString());
			return;
		}
		array<vector> ra = rest.Get("EP_Arm_" + sd);
		array<vector> rc = rest.Get("EP_Cup_" + sd);
		vector Ra[4], Rc[4];
		for (int i = 0; i < 3; i++)
		{
			Ra[i] = ra[i];
			Rc[i] = rc[i];
		}
		vector hinge = Vector(0.171 * s, 0.245, 0.954);
		vector rsw[4], rsp[4], rarm[4], ryw[4], rsn[4], rg[4], da[4], dc[4];
		RotAxis(MapDir("1 0 0", own), -swing * Math.DEG2RAD, rsw);
		RotAxis(MapDir(hinge, own), s * splay * Math.DEG2RAD, rsp);
		Mul(rsw, rsp, rarm);
		RotAxis(MapDir("0 0 1", own), -s * yaw * Math.DEG2RAD, ryw);
		RotAxis(MapDir(Vector(s, 0, 0), own), -spin * Math.DEG2RAD, rsn);
		Mul(ryw, rsn, rg);
		Conj(Ra, rarm, da);
		Conj(Rc, rg, dc);
		anim.SetBoneMatrix(ear, ia, da);
		anim.SetBoneMatrix(ear, ic, dc);
	}

	ref array<ref map<string, ref array<vector> > > m_aRest = {};

	void CaptureRest(IEntity ear, out map<string, ref array<vector> > rest)
	{
		rest = new map<string, ref array<vector> >();
		Animation anim = ear.GetAnimation();
		if (!anim)
			return;
		array<string> names = {};
		anim.GetBoneNames(names);
		foreach (string n : names)
		{
			if (!n.StartsWith("EP_"))
				continue;
			vector m[4];
			anim.GetBoneMatrix(anim.GetBoneIndex(n), m);
			array<vector> a = {m[0], m[1], m[2], m[3]};
			rest.Insert(n, a);
		}
	}

	void LogEar(string tag, IEntity ear, IEntity man)
	{
		Animation anim = ear.GetAnimation();
		if (!anim)
		{
			Log(tag + " no Animation on ear-pro entity");
			return;
		}
		array<string> names = {};
		anim.GetBoneNames(names);
		string ep;
		foreach (string n : names)
			if (n.StartsWith("EP_"))
				ep += n + " ";
		Log(string.Format("%1 bones %2 EP: %3", tag, names.Count(), ep));
		foreach (string n : names)
		{
			if (!n.StartsWith("EP_"))
				continue;
			vector m[4], l[4];
			anim.GetBoneMatrix(anim.GetBoneIndex(n), m);
			anim.GetBoneLocalMatrix(anim.GetBoneIndex(n), l);
			Log(string.Format("%1   %2 model %3 | local %4", tag, n, M2S(m), M2S(l)));
		}
		vector ew[4];
		ear.GetWorldTransform(ew);
		vector hb = BoneWorld(man, "Head");
		Log(string.Format("%1 ear origin %2 head bone %3 delta %4 parent %5", tag, ew[3], hb, ew[3] - hb, ear.GetParent()));
	}

	//------------------------------------------------------------------------------------------------ camera
	protected void Cam(vector at, vector eye, float fov)
	{
		if (!m_Camera)
		{
			EntitySpawnParams cp();
			cp.TransformMode = ETransformMode.WORLD;
			m_Camera = PLHM_TestCamera.Cast(GetGame().SpawnEntity(PLHM_TestCamera, GetWorld(), cp));
		}
		m_Camera.SetFOVDegree(fov);
		m_Camera.SetNearPlane(0.01);
		if (GetGame().GetCameraManager().CurrentCamera() != m_Camera)
			GetGame().GetCameraManager().SetCamera(m_Camera);
		vector cm[4];
		Math3D.DirectionAndUpMatrix(at - eye, vector.Up, cm);
		cm[3] = eye;
		m_Camera.SetWorldTransform(cm);
	}

	protected void Aim(IEntity c, string view)
	{
		vector t[4];
		c.GetWorldTransform(t);
		vector r = t[0];
		vector f = t[2];
		vector h = BoneWorld(c, "Head") + "0 0.06 0";
		if (view == "left")
			Cam(h, h - r * 0.75 + "0 0.03 0", 32);
		else if (view == "right")
			Cam(h, h + r * 0.75 + "0 0.03 0", 32);
		else if (view == "rear")
			Cam(h, h - f * 0.75 + "0 0.10 0", 32);
		else if (view == "front")
			Cam(h, h + f * 0.75 + "0 0.03 0", 32);
		else if (view == "rear34L")
			Cam(h, h - f * 0.55 - r * 0.55 + "0 0.22 0", 32);
		else if (view == "rear34R")
			Cam(h, h - f * 0.55 + r * 0.55 + "0 0.22 0", 32);
		else if (view == "top")
			Cam(h, h - f * 0.25 + "0 0.8 0", 32);
	}

	protected void Queue(IEntity e, string view, string scene)
	{
		m_aQEnt.Insert(e);
		m_aQView.Insert(view);
		m_aQScene.Insert(scene);
	}

	//! returns true while the shot queue is busy
	protected bool ServeShots()
	{
		if (m_aQEnt.IsEmpty())
			return false;
		if (m_iCamSince < 0)
		{
			Aim(m_aQEnt[0], m_aQView[0]);
			m_iCamSince = m_iFrame;
			return true;
		}
		Aim(m_aQEnt[0], m_aQView[0]);
		if (m_iFrame - m_iCamSince < 10)
			return true;
		string f = string.Format("$profile:plhmshots/%1_%2_%3.bmp", m_iSnap.ToString(4), m_aQScene[0], m_aQView[0]);
		m_iSnap++;
		Log(string.Format("[SNAP] %1 ok=%2", f, System.MakeScreenshot(f)));
		m_aQEnt.RemoveOrdered(0);
		m_aQView.RemoveOrdered(0);
		m_aQScene.RemoveOrdered(0);
		m_iCamSince = -1;
		return true;
	}

	protected void HoldFor(float secs, int frames = 10)
	{
		m_fNext = Now() + secs;
		m_iWaitFrame = m_iFrame + frames;
	}

	protected bool IsHolding()
	{
		return Now() < m_fNext || m_iFrame < m_iWaitFrame;
	}

	//------------------------------------------------------------------------------------------------ main
	override void EOnFrame(IEntity owner, float timeSlice)
	{
		m_iFrame++;
		if (m_sMode == "mpdemo")
		{
			StepMpDemo();
			return;
		}
		if (m_sMode == "idle")
			return;
		if (m_sMode == "clips")
		{
			StepClips();
			return;
		}
		if (m_sMode == "rollout")
		{
			StepRollout();
			return;
		}
		if (m_sMode == "fitdiag")
		{
			StepFitDiag();
			return;
		}
		if (m_sMode == "propdiag")
		{
			StepPropDiag();
			return;
		}
		if (m_bReapply)
			ApplyProbe(m_iProbeOrder);
		if (ServeShots() || IsHolding())
			return;
		if (m_bAnimating)
		{
			TickHand();
			return;
		}
		if (TickObserve())
			return;
		if (m_sMode == "gdiag")
		{
			StepGDiag();
			return;
		}
		if (m_sMode == "bones" || m_sMode == "probe" || m_sMode == "probe2")
			StepBones();
		else if (m_sMode == "hand")
			StepHand();
	}


	//------------------------------------------------------------------------------------------------ mpdemo (dedicated server only)
	// Equips every player (and each respawn) with the real SF helmet + Ops-Core AMP, spawns a demo box (ear-pro actions
	// + kit swaps) and two dummy soldiers cycling the ear-pro requests: AMP on an SF helmet, ComTacs on an XP helmet.
	// Everything goes through the shipping path (PLHM_EarProService / PLHM_EarProComponent replication).
	static const ResourceName DEMO_BOX = "{DC181468AC178F7F}Prefabs/PLHM_Test/PLHM_DemoBox.et";
	static const ResourceName DEMO_AMP = "{FF1A872BD2B7EBE7}Prefabs/EarPro/OpsCore AMP.et";
	static const ResourceName DEMO_CT_XP = "{E58BFD77DC660376}Prefabs/EarPro/Comtacs (Tan) (XP).et";
	protected int m_iDemo;
	protected float m_fDemoNext = 3;
	protected float m_fDemoPlayersNext;
	protected ref array<IEntity> m_aDemoDummies = {};
	protected int m_iDemoCycles;
	protected ref array<IEntity> m_aDemoSeen = {};
	protected ref array<float> m_aDemoSeenT = {};
	protected ref array<int> m_aDemoStage = {};

	protected vector Ground(float x, float z)
	{
		return Vector(x, GetWorld().GetSurfaceY(x, z), z);
	}

	protected void StepMpDemo()
	{
		if (!Replication.IsServer())
			return;
		float now = Now();
		if (now >= m_fDemoPlayersNext)
		{
			m_fDemoPlayersNext = now + 1;
			DemoPlayers(now);
		}
		if (now < m_fDemoNext)
			return;
		switch (m_iDemo)
		{
			case 0:
			{
				IEntity box = Spawn(DEMO_BOX, Ground(1028.3, 2428.2), 90);
				m_aDemoDummies.Insert(Spawn(MANNEQUIN, Ground(1030, 2430.5), 180));
				m_aDemoDummies.Insert(Spawn(MANNEQUIN, Ground(1031.6, 2430.5), 180));
				Log(string.Format("[MPDEMO] box %1 dummies %2", box, m_aDemoDummies.Count()));
				m_fDemoNext = now + 4;
				break;
			}
			case 1:
				Log("[MPDEMO] dummy A helmet -> " + Wear(m_aDemoDummies[0], H_SF).ToString());
				Log("[MPDEMO] dummy B helmet -> " + Wear(m_aDemoDummies[1], H_XP).ToString());
				m_fDemoNext = now + 2;
				break;
			case 2:
				Log("[MPDEMO] dummy A ear-pro -> " + InsertIntoHelmet(m_aDemoDummies[0], DEMO_AMP).ToString());
				Log("[MPDEMO] dummy B ear-pro -> " + InsertIntoHelmet(m_aDemoDummies[1], DEMO_CT_XP).ToString());
				Log("[MPDEMO] ready");
				m_fDemoNext = now + 5;
				break;
			default:
			{
				// stow both, deploy both, vent both, close both, right cup up, right cup down
				int k = m_iDemoCycles % 6;
				int req = PLHM_EEarProRequest.TOGGLE_STOW;
				int mask = 3;
				if (k == 2 || k == 3)
					req = PLHM_EEarProRequest.TOGGLE_VENT;
				if (k >= 4)
					mask = 2;
				foreach (IEntity d : m_aDemoDummies)
				{
					string why;
					bool ok = PLHM_EarProService.ServerRequest(d, req, mask, why);
					if (m_iDemoCycles <= 12 || !ok)
						Log(string.Format("[MPDEMO] dummy request %1/%2 -> %3", req, mask, why));
				}
				m_iDemoCycles++;
				m_fDemoNext = now + 9;
				return;
			}
		}
		m_iDemo++;
	}

	protected void DemoPlayers(float now)
	{
		array<int> ids = {};
		GetGame().GetPlayerManager().GetPlayers(ids);
		foreach (int pid : ids)
		{
			IEntity ch = GetGame().GetPlayerManager().GetPlayerControlledEntity(pid);
			ChimeraCharacter cc = ChimeraCharacter.Cast(ch);
			if (!cc || !cc.GetCharacterController() || cc.GetCharacterController().GetLifeState() != ECharacterLifeState.ALIVE)
				continue;
			int i = m_aDemoSeen.Find(ch);
			if (i == -1)
			{
				m_aDemoSeen.Insert(ch);
				m_aDemoSeenT.Insert(now);
				m_aDemoStage.Insert(0);
				continue;
			}
			float age = now - m_aDemoSeenT[i];
			if (m_aDemoStage[i] == 0 && age > 3)
			{
				m_aDemoStage[i] = 1;
				Log(string.Format("[MPDEMO] player %1 helmet -> %2", pid, Wear(ch, H_SF)));
			}
			else if (m_aDemoStage[i] == 1 && age > 5)
			{
				m_aDemoStage[i] = 2;
				Log(string.Format("[MPDEMO] player %1 ear-pro -> %2", pid, InsertIntoHelmet(ch, DEMO_AMP)));
			}
		}
	}


	//------------------------------------------------------------------------------------------------ clips (SP, player): every request through the shipping service
	// -plhmMode clips : armed pass (rifle in hand: lowered + left hand only, both cups in sequence), then unarmed pass
	// (own hand per cup, both hands together). Logs [CLIP] knuckle->grip distances, screenshots per request.
	protected int m_iC;
	protected int m_iCStep;
	protected float m_fCStart;
	protected float m_fCLog;
	protected int m_iCShot;
	protected ref array<int> m_aCReq = {8, 8, 9, 9, 8, 9, 8, 8, 0, 8, 8, 9, 9, 8, 8, 9, 9};
	protected ref array<int> m_aCMask = {3, 3, 3, 3, 2, 3, 3, 3, 0, 3, 3, 3, 3, 2, 2, 1, 1};
	protected ref array<float> m_aCHold = {7.8, 8.4, 5.0, 5.0, 4.0, 2.8, 3.8, 8.4, 2.5, 3.6, 3.8, 2.4, 2.4, 3.4, 3.6, 2.4, 2.4};
	protected ref array<float> m_aCShotT = {0.9, 1.6, 2.4};

	protected void BodyCam(IEntity c, bool rightSide)
	{
		vector t[4];
		c.GetWorldTransform(t);
		vector r = t[0];
		vector f = t[2];
		vector h = BoneWorld(c, "Head") - "0 0.18 0";
		float sx = -1;
		if (rightSide)
			sx = 1;
		Cam(h, h + f * 1.05 + r * (0.85 * sx) + "0 0.12 0", 42);
	}

	protected vector GripWorldSide(IEntity ear, int side)
	{
		string b = "EP_Cup_L";
		vector grip = "0.121 0.02358 -0.00699";
		if (side == 2)
		{
			b = "EP_Cup_R";
			grip = "-0.121 0.02358 -0.00699";
		}
		Animation anim = ear.GetAnimation();
		int ic = anim.GetBoneIndex(b);
		array<vector> rc = m_aRest[0].Get(b);
		if (ic == -1 || !rc)
			return vector.Zero;
		vector now[4];
		anim.GetBoneMatrix(ic, now);
		vector rest[4];
		for (int i = 0; i < 4; i++)
			rest[i] = rc[i];
		vector local = grip.InvMultiply4(rest);
		vector posed = local.Multiply4(now);
		return ear.CoordToParent(posed);
	}

	protected void StepClips()
	{
		if (m_iC == 99)
			return;
		IEntity man;
		if (!m_aMen.IsEmpty())
			man = m_aMen[0];
		if (m_iC >= 6 && m_iCStep < m_aCReq.Count())
		{
			float t = Now() - m_fCStart;
			int mask = m_aCMask[m_iCStep];
			BodyCam(man, mask == 2);
			if (t - m_fCLog >= 0.1 && t < m_aCHold[m_iCStep])
			{
				m_fCLog = t;
				IEntity ear = m_aEar[0];
				vector gl = GripWorldSide(ear, 1);
				vector gr = GripWorldSide(ear, 2);
				vector kl = BoneWorld(man, "LeftHandMiddle2");
				vector kr = BoneWorld(man, "RightHandMiddle2");
				CharacterControllerComponent cc = ChimeraCharacter.Cast(man).GetCharacterController();
				Log(string.Format("[CLIP] step %1 t=%2 LkL %3 LkR %4 RkR %5 RkL %6 gadget %7 raised %8", m_iCStep, t,
					(int)(vector.Distance(kl, gl) * 1000), (int)(vector.Distance(kl, gr) * 1000), (int)(vector.Distance(kr, gr) * 1000),
					(int)(vector.Distance(kr, gl) * 1000), cc.IsGadgetInHands(), cc.IsWeaponRaised()));
			}
			if (m_iCShot < m_aCShotT.Count() && t >= m_aCShotT[m_iCShot] && t < m_aCHold[m_iCStep])
			{
				string f = string.Format("$profile:plhmshots/%1_clip%2_t%3.bmp", m_iSnap.ToString(4), m_iCStep, (int)(m_aCShotT[m_iCShot] * 100));
				m_iSnap++;
				Log(string.Format("[SNAP] %1 ok=%2", f, System.MakeScreenshot(f)));
				m_iCShot++;
			}
			if (t < m_aCHold[m_iCStep])
				return;
			m_iCStep++;
			StartClipStep();
			return;
		}
		if (IsHolding())
			return;
		switch (m_iC)
		{
			case 0:
				HoldFor(5, 120);
				break;
			case 1:
			{
				IEntity pc = null;
				if (GetGame().GetPlayerController())
					pc = GetGame().GetPlayerController().GetControlledEntity();
				if (!pc)
				{
					HoldFor(1, 10);
					return;
				}
				m_aMen.Insert(pc);
				Log("player character " + pc.ToString());
				HoldFor(3, 60);
				break;
			}
			case 2:
				Log("wear test helmet -> " + Wear(m_aMen[0], TEST_HELMET).ToString());
				HoldFor(2, 30);
				break;
			case 3:
				m_aEar.Insert(InsertIntoHelmet(m_aMen[0], AMP_OWN));
				HoldFor(2, 40);
				break;
			case 4:
			{
				map<string, ref array<vector> > rest;
				CaptureRest(m_aEar[0], rest);
				m_aRest.Insert(rest);
				Log(string.Format("rest bones %1 armed %2", rest.Count(), PLHM_EarProService.IsArmed(m_aMen[0])));
				BodyCam(m_aMen[0], false);
				HoldFor(1.5, 40);
				break;
			}
			case 5:
				m_iC = 6;
				m_iCStep = 0;
				StartClipStep();
				return;
			default:
				if (m_iCStep >= m_aCReq.Count())
				{
					Log("DONE");
					m_iC = 99;
				}
				return;
		}
		m_iC++;
	}

	protected void StartClipStep()
	{
		m_fCStart = Now();
		m_fCLog = -1;
		m_iCShot = 0;
		if (m_iCStep >= m_aCReq.Count())
			return;
		int req = m_aCReq[m_iCStep];
		if (req == 0)
		{
			CharacterControllerComponent cc = ChimeraCharacter.Cast(m_aMen[0]).GetCharacterController();
			Log("[CLIP] holster -> " + cc.SelectWeapon(null).ToString());
			return;
		}
		string why;
		bool ok = PLHM_EarProService.ServerRequest(m_aMen[0], req, m_aCMask[m_iCStep], why);
		PLHM_EarProComponent ep = PLHM_EarProService.FindEarPro(m_aMen[0]);
		int sl = -1;
		int sr = -1;
		if (ep)
		{
			sl = ep.GetState(1);
			sr = ep.GetState(2);
		}
		Log(string.Format("[CLIP] step %1 request %2 mask %3 -> %4 (%5) state L%6 R%7", m_iCStep, req, m_aCMask[m_iCStep], ok, why, sl, sr));
	}


	//------------------------------------------------------------------------------------------------ rollout (SP, player)
	// -plhmMode rollout : FIT = every shipping ear-pro prefab on its helmet family, screenshots (left + rear34R);
	// CLIPS = per clip set: armed right cup (left hand over the top) stow + deploy, then unarmed both-hands stow / deploy /
	// vent / close. [RO] logs knuckle -> grip distances per clip set.
	static const ResourceName H_SF = "{AF457DB4423C4107}Prefabs/Helmets/SF V2 Helmets/SF_Helmet_AOR1 (base dont touch).et";
	static const ResourceName H_MAR = "{8CACB79B18F0B611}Prefabs/Helmets/Maritime/Maritime_Helmet.et";
	static const ResourceName H_XP = "{930546500F935E9B}Prefabs/Helmets/XP/XP_Helmet.et";
	protected ref array<ResourceName> m_aFitEar = {
		"{FF1A872BD2B7EBE7}Prefabs/EarPro/OpsCore AMP.et", "{24F4B4890254B178}Prefabs/EarPro/OpsCore AMP (Black).et", "{9A87F4B7CC132693}Prefabs/EarPro/OpsCore AMP (RG).et",
		"{25181C2D4A143EA2}Prefabs/EarPro/OpsCore AMP (Maritime).et", "{746908C976D7F138}Prefabs/EarPro/OpsCore AMP (Black) (Maritime).et", "{E7FD4A2CDA0E1B6C}Prefabs/EarPro/OpsCore AMP (RG) (Maritime).et",
		"{C21E8EE03785D12D}Prefabs/EarPro/OpsCore AMP (XP).et", "{2CB06DA785DF21EA}Prefabs/EarPro/OpsCore AMP (Black) (XP).et", "{F9E45EB7365C9129}Prefabs/EarPro/OpsCore AMP (RG) (XP).et",
		"{84312A6ACEF2297C}Prefabs/EarPro/Comtac VI.et", "{798456A85C7DCC58}Prefabs/EarPro/Comtac VI (Maritime).et", "{FEA34161C59A71E2}Prefabs/EarPro/Comtac VI (XP).et",
		"{86404BF81BEA3F3E}Prefabs/EarPro/Comtacs (Green).et", "{466B33405EFDAB08}Prefabs/EarPro/Comtacs (Green) (Maritime).et", "{90B1EEF31CA16352}Prefabs/EarPro/Comtacs (Green) (XP).et",
		"{DCFC388467502D9C}Prefabs/EarPro/Comtacs (Grey).et", "{54835580F01FF5B1}Prefabs/EarPro/Comtacs (Grey) (Maritime).et", "{33A39053FC7BDEFF}Prefabs/EarPro/Comtacs (Grey) (XP).et",
		"{8A5E5506477023D7}Prefabs/EarPro/Comtacs (RG).et", "{3EE945F0281C1660}Prefabs/EarPro/Comtacs (RG) (Maritime).et", "{200A917574D615D5}Prefabs/EarPro/Comtacs (RG) (XP).et",
		"{228DE75A7C0B9E13}Prefabs/EarPro/Comtacs (Tan).et", "{64C8E131E916CBAD}Prefabs/EarPro/Comtacs (Tan) (Maritime).et", "{E58BFD77DC660376}Prefabs/EarPro/Comtacs (Tan) (XP).et"};
	// helmet family per fit item: 0 SF, 1 Maritime, 2 XP
	protected ref array<int> m_aFitFam = {0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2};
	// one ear-pro per clip set (index into m_aFitEar) and its grip points (out fwd z, Punisherbody frame)
	protected ref array<int> m_aSetItem = {0, 6, 12, 14, 9, 11};
	protected ref array<vector> m_aSetGrip = {"0.121 -0.025 1.642", "0.121 -0.023 1.6275", "0.1221 -0.0045 1.6435", "0.1203 -0.0215 1.6276", "0.122 -0.0179 1.6408", "0.122 -0.0179 1.632"};
	protected ref array<vector> m_aSetXGrip = {"0.121 -0.02 1.655", "0.121 -0.018 1.6405", "0.1221 -0.0001 1.6562", "0.1203 -0.0171 1.6403", "0.122 -0.0135 1.6535", "0.122 -0.0135 1.6447"};
	protected int m_iRo;
	protected int m_iRoItem;
	protected int m_iRoSet;
	protected int m_iRoReq;
	protected bool m_bRoArmed = true;
	protected float m_fRoStart;
	protected float m_fRoLog;
	protected int m_iRoShot;
	protected IEntity m_RoEar;
	protected ref map<string, ref array<vector> > m_RoRest;
	protected ref array<int> m_aRoArmedReq = {8, 8};
	protected ref array<int> m_aRoArmedMask = {3, 3};
	protected ref array<float> m_aRoArmedHold = {6.5, 6.8};
	protected ref array<int> m_aRoReq = {8, 8, 9, 9};
	protected ref array<int> m_aRoMask = {3, 3, 3, 3};
	protected ref array<float> m_aRoHold = {3.6, 3.8, 2.4, 2.4};

	protected ResourceName FamHelmet(int fam)
	{
		if (fam == 1)
			return H_MAR;
		if (fam == 2)
			return H_XP;
		return H_SF;
	}

	//! Punisherbody grip (out, fwd, z) -> item model space of the Head-pivot rig (side 1 = L, 2 = R)
	static vector GripItem(vector g, int side)
	{
		float x = g[0];
		if (side == 2)
			x = -g[0];
		return Vector(x, g[2] - 1.61842, -(g[1] + 0.03199));
	}

	protected vector GripWorldOf(IEntity ear, int side, vector gripItem)
	{
		string b = "EP_Cup_L";
		if (side == 2)
			b = "EP_Cup_R";
		Animation anim = ear.GetAnimation();
		int ic = anim.GetBoneIndex(b);
		array<vector> rc = m_RoRest.Get(b);
		if (ic == -1 || !rc)
			return vector.Zero;
		vector now[4];
		anim.GetBoneMatrix(ic, now);
		vector rest[4];
		for (int i = 0; i < 4; i++)
			rest[i] = rc[i];
		vector local = gripItem.InvMultiply4(rest);
		return ear.CoordToParent(local.Multiply4(now));
	}

	protected void RoMount(int item)
	{
		Wear(m_aMen[0], FamHelmet(m_aFitFam[item]));
		m_RoEar = null;
		GetGame().GetCallqueue().CallLater(RoInsert, 1500, false, item);
	}

	protected void RoInsert(int item)
	{
		m_RoEar = InsertIntoHelmet(m_aMen[0], m_aFitEar[item]);
	}

	protected string RoView()
	{
		if (m_iRoShot == 1)
			return "rear34R";
		return "left";
	}

	protected void StepRollout()
	{
		if (m_iRo == 99)
			return;
		IEntity man;
		if (!m_aMen.IsEmpty())
			man = m_aMen[0];
		float now = Now();
		if (m_iRo == 0)
		{
			if (IsHolding())
				return;
			HoldFor(5, 120);
			m_iRo = 1;
			return;
		}
		if (m_iRo == 1)
		{
			if (IsHolding())
				return;
			IEntity pc = null;
			if (GetGame().GetPlayerController())
				pc = GetGame().GetPlayerController().GetControlledEntity();
			if (!pc)
			{
				HoldFor(1, 10);
				return;
			}
			m_aMen.Insert(pc);
			Log("player character " + pc.ToString());
			// third person: OUTLAW_FirstPersonHideComponent hides the wearer's own ear-pro / helmet in first person
			ChimeraCharacter.Cast(pc).GetCharacterController().SetInThirdPersonView(true);
			HoldFor(3, 60);
			m_iRo = 2;
			m_iRoItem = 0;
			return;
		}
		if (m_iRo == 2)		// FIT: mount item
		{
			if (IsHolding())
				return;
			if (m_iRoItem >= m_aFitEar.Count())
			{
				m_iRo = 10;
				m_iRoSet = 0;
				return;
			}
			RoMount(m_iRoItem);
			HoldFor(3.2, 60);
			m_iRo = 3;
			return;
		}
		if (m_iRo == 3)		// FIT: aim
		{
			if (IsHolding())
				return;
			Aim(man, RoView());
			HoldFor(0.35, 8);
			m_iRo = 4;
			return;
		}
		if (m_iRo == 4)		// FIT: shot
		{
			if (IsHolding())
				return;
			string f = string.Format("$profile:plhmshots/%1_fit%2_%3.bmp", m_iSnap.ToString(4), m_iRoItem.ToString(2), RoView());
			m_iSnap++;
			PLHM_EarProComponent ep = PLHM_EarProService.FindEarPro(man);
			Log(string.Format("[RO] fit %1 %2 shot %3 ok=%4 component=%5", m_iRoItem, m_aFitEar[m_iRoItem], RoView(), System.MakeScreenshot(f), ep != null));
			m_iRoShot++;
			if (m_iRoShot >= 2)
			{
				m_iRoShot = 0;
				m_iRoItem++;
				m_iRo = 2;
			}
			else
			{
				m_iRo = 3;
			}
			return;
		}
		if (m_iRo == 10)	// CLIPS: mount the clip set's ear-pro
		{
			if (IsHolding())
				return;
			if (m_iRoSet >= m_aSetItem.Count())
			{
				if (m_bRoArmed)
				{
					m_bRoArmed = false;
					Log("[RO] holster -> " + ChimeraCharacter.Cast(man).GetCharacterController().SelectWeapon(null).ToString());
					m_iRoSet = 0;
					HoldFor(2, 30);
					return;
				}
				Log("DONE");
				m_iRo = 99;
				return;
			}
			RoMount(m_aSetItem[m_iRoSet]);
			HoldFor(3.2, 60);
			m_iRo = 11;
			return;
		}
		if (m_iRo == 11)	// capture rest, first request
		{
			if (IsHolding())
				return;
			CaptureRest(m_RoEar, m_RoRest);
			m_iRoReq = 0;
			RoStartReq();
			m_iRo = 12;
			return;
		}
		if (m_iRo == 12)
		{
			float t = now - m_fRoStart;
			BodyCam(man, m_bRoArmed);
			float hold = m_aRoHold[m_iRoReq];
			if (m_bRoArmed)
				hold = m_aRoArmedHold[m_iRoReq];
			if (t - m_fRoLog >= 0.1 && t < hold)
			{
				m_fRoLog = t;
				vector g = m_aSetGrip[m_iRoSet];
				vector xg = m_aSetXGrip[m_iRoSet];
				vector gl = GripWorldOf(m_RoEar, 1, GripItem(g, 1));
				vector gr = GripWorldOf(m_RoEar, 2, GripItem(g, 2));
				vector gx = GripWorldOf(m_RoEar, 2, GripItem(xg, 2));
				vector kl = BoneWorld(man, "LeftHandMiddle2");
				vector kr = BoneWorld(man, "RightHandMiddle2");
				CharacterControllerComponent rcc = ChimeraCharacter.Cast(man).GetCharacterController();
				bool wpn = rcc.GetWeaponManagerComponent() && rcc.GetWeaponManagerComponent().GetCurrentWeapon();
				Log(string.Format("[RO] set %1 armed %2 req %3 t=%4 LkL %5 RkR %6 LkRx %7 weapon %8 gadget %9", m_iRoSet, m_bRoArmed, m_iRoReq, t,
					(int)(vector.Distance(kl, gl) * 1000), (int)(vector.Distance(kr, gr) * 1000), (int)(vector.Distance(kl, gx) * 1000), wpn, rcc.IsGadgetInHands()));
			}
			float shot0 = 0.9;
			if (m_bRoArmed)
				shot0 = 2.4;
			if (m_iRoShot < 2 && t >= shot0 + m_iRoShot * 0.7 && t < hold)
			{
				string f2 = string.Format("$profile:plhmshots/%1_set%2_%3_r%4_t%5.bmp", m_iSnap.ToString(4), m_iRoSet, m_bRoArmed, m_iRoReq, m_iRoShot);
				m_iSnap++;
				System.MakeScreenshot(f2);
				m_iRoShot++;
			}
			if (t < hold)
				return;
			m_iRoReq++;
			int n = m_aRoReq.Count();
			if (m_bRoArmed)
				n = m_aRoArmedReq.Count();
			if (m_iRoReq >= n)
			{
				m_iRoSet++;
				m_iRo = 10;
				return;
			}
			RoStartReq();
		}
	}

	protected void RoStartReq()
	{
		m_fRoStart = Now();
		m_fRoLog = -1;
		m_iRoShot = 0;
		int req = m_aRoReq[m_iRoReq];
		int mask = m_aRoMask[m_iRoReq];
		if (m_bRoArmed)
		{
			req = m_aRoArmedReq[m_iRoReq];
			mask = m_aRoArmedMask[m_iRoReq];
		}
		string why;
		bool ok = PLHM_EarProService.ServerRequest(m_aMen[0], req, mask, why);
		Log(string.Format("[RO] set %1 armed %2 req %3 (%4/%5) -> %6 (%7)", m_iRoSet, m_bRoArmed, m_iRoReq, req, mask, ok, why));
	}


	//------------------------------------------------------------------------------------------------ fitdiag: why mounted ear-pros are not drawn
	protected int m_iFd;
	protected ref array<int> m_aFdItems = {1, 12, 0};

	protected void FdLog(string tag)
	{
		IEntity man = m_aMen[0];
		IEntity ear = m_RoEar;
		CharacterControllerComponent cc = ChimeraCharacter.Cast(man).GetCharacterController();
		if (!ear)
		{
			Log("[FD] " + tag + " no ear entity");
			return;
		}
		ParametricMaterialInstanceComponent pm = ParametricMaterialInstanceComponent.Cast(ear.FindComponent(ParametricMaterialInstanceComponent));
		int alpha = -1;
		if (pm)
			alpha = pm.GetUserAlphaTestParam();
		string vobj = "none";
		if (ear.GetVObject())
			vobj = ear.GetVObject().GetResourceName();
		int vcf = ear.SetVComponentFlags(0);
		vector ew[4];
		ear.GetWorldTransform(ew);
		Log(string.Format("[FD] %1 tp=%2 visible=%3 alpha=%4 inheritSkel=%5 parent=%6 dHead=%7 vobj=%8", tag, cc.IsInThirdPersonView(),
			(ear.GetFlags() & EntityFlags.VISIBLE) != 0, alpha, (vcf & VCFlags.INHERIT_PARENT_SKELETON) != 0, ear.GetParent(),
			vector.Distance(ew[3], BoneWorld(man, "Head")), vobj));
	}

	protected void StepFitDiag()
	{
		if (IsHolding())
			return;
		IEntity man;
		if (!m_aMen.IsEmpty())
			man = m_aMen[0];
		switch (m_iFd)
		{
			case 0:
				HoldFor(5, 120);
				break;
			case 1:
			{
				IEntity pc = null;
				if (GetGame().GetPlayerController())
					pc = GetGame().GetPlayerController().GetControlledEntity();
				if (!pc)
				{
					HoldFor(1, 10);
					return;
				}
				m_aMen.Insert(pc);
				HoldFor(3, 60);
				break;
			}
			default:
			{
				int k = m_iFd - 2;
				int item = k / 3;
				int phase = k % 3;
				if (item >= m_aFdItems.Count())
				{
					Log("DONE");
					m_iFd = 999;
					return;
				}
				if (phase == 0)
				{
					RoMount(m_aFdItems[item]);
					HoldFor(3.5, 60);
				}
				else if (phase == 1)
				{
					FdLog(string.Format("item %1 as-is", m_aFdItems[item]));
					Aim(man, "left");
					GetGame().GetCallqueue().CallLater(FdShot, 400, false, string.Format("item%1_asis", m_aFdItems[item]));
					ChimeraCharacter.Cast(man).GetCharacterController().SetInThirdPersonView(true);
					HoldFor(1.5, 30);
				}
				else
				{
					FdLog(string.Format("item %1 after TP", m_aFdItems[item]));
					Aim(man, "left");
					GetGame().GetCallqueue().CallLater(FdShot, 400, false, string.Format("item%1_tp", m_aFdItems[item]));
					ChimeraCharacter.Cast(man).GetCharacterController().SetInThirdPersonView(false);
					HoldFor(1.0, 20);
				}
				break;
			}
		}
		if (m_iFd < 999)
			m_iFd++;
	}

	protected void FdShot(string tag)
	{
		string f = string.Format("$profile:plhmshots/%1_fd_%2.bmp", m_iSnap.ToString(4), tag);
		m_iSnap++;
		Log(string.Format("[SNAP] %1 ok=%2", f, System.MakeScreenshot(f)));
	}


	//------------------------------------------------------------------------------------------------ propdiag: where vanilla holds the rifle while a left-hand gadget is out
	// logs Spine5-relative matrices of RightHandProp (the rifle attach bone) and the rifle's own transform relative to it
	protected int m_iPd;

	protected void PdLogBone(string tag, IEntity man, string bone)
	{
		Animation anim = man.GetAnimation();
		int bs = anim.GetBoneIndex("Spine5");
		int bp = anim.GetBoneIndex(bone);
		vector S[4], P[4];
		anim.GetBoneMatrix(bs, S);
		anim.GetBoneMatrix(bp, P);
		// relative = inverse(S) * P, columns
		vector rel[4];
		for (int j = 0; j < 3; j++)
			rel[j] = Vector(vector.Dot(P[j], S[0]), vector.Dot(P[j], S[1]), vector.Dot(P[j], S[2]));
		vector d = P[3] - S[3];
		rel[3] = Vector(vector.Dot(d, S[0]), vector.Dot(d, S[1]), vector.Dot(d, S[2]));
		Log(string.Format("[PD] %1 %2 relSpine5 x %3 y %4 z %5 t %6", tag, bone, rel[0], rel[1], rel[2], rel[3]));
	}

	protected void PdLog(string tag)
	{
		IEntity man = m_aMen[0];
		PdLogBone(tag, man, "RightHandProp");
		PdLogBone(tag, man, "RightHand");
		CharacterControllerComponent cc = ChimeraCharacter.Cast(man).GetCharacterController();
		IEntity w = null;
		if (cc.GetWeaponManagerComponent() && cc.GetWeaponManagerComponent().GetCurrentWeapon())
			w = cc.GetWeaponManagerComponent().GetCurrentWeapon().GetOwner();
		if (w)
		{
			vector ww[4];
			w.GetWorldTransform(ww);
			vector pw = BoneWorld(man, "RightHandProp");
			Log(string.Format("[PD] %1 weapon origin - prop %2 mm, weapon parent %3", tag, (int)(vector.Distance(ww[3], pw) * 1000), w.GetParent()));
		}
	}

	protected void StepPropDiag()
	{
		if (IsHolding() || m_iPd >= 99)
			return;
		IEntity man;
		if (!m_aMen.IsEmpty())
			man = m_aMen[0];
		switch (m_iPd)
		{
			case 0:
				HoldFor(5, 120);
				break;
			case 1:
			{
				IEntity pc = null;
				if (GetGame().GetPlayerController())
					pc = GetGame().GetPlayerController().GetControlledEntity();
				if (!pc)
				{
					HoldFor(1, 10);
					return;
				}
				m_aMen.Insert(pc);
				ChimeraCharacter.Cast(pc).GetCharacterController().SetInThirdPersonView(true);
				HoldFor(3, 60);
				break;
			}
			case 2:
				RoMount(0);
				HoldFor(3.5, 60);
				break;
			case 3:
				PdLog("idle_armed");
				break;
			case 4:
			{
				string why;
				Log("[PD] vent L -> " + PLHM_EarProService.ServerRequest(man, 9, 1, why).ToString() + " " + why);
				HoldFor(0.9, 10);
				break;
			}
			case 5:
				PdLog("gadget_t09");
				BodyCam(man, true);
				GetGame().GetCallqueue().CallLater(FdShot, 100, false, "gadget_hold");
				HoldFor(0.3, 5);
				break;
			case 6:
				PdLog("gadget_t12");
				HoldFor(3, 40);
				break;
			default:
				Log("DONE");
				m_iPd = 99;
				return;
		}
		m_iPd++;
	}

	//------------------------------------------------------------------------------------------------ hand (proxy gadget + clip)
	static const ResourceName PROXY_RAISE_L = "{76F4C8F4B05F7003}Prefabs/EarPro/Hands/PLHM_EarProHand_RaiseL.et";
	protected int m_iH;
	protected bool m_bAnimating;
	protected float m_fT0;
	protected float m_fLastLog = -1;
	protected IEntity m_Proxy;
	protected string m_sView = "left";
	protected ref array<float> m_aShotT = {0.15, 0.35, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.3, 2.6};
	protected int m_iShotIdx;
	protected bool m_bReleased;
	// raise_L timeline (clip seconds) from OUTLAWHELMETS/_earpro/build/anim/plhm_amp_raise_L_timeline.json
	protected ref array<float> m_kSplay = {0.45, 0, 0.736, 44, 1.36, 44, 1.698, 24};
	protected ref array<float> m_kSwing = {0.645, 0, 1.516, 161.5};
	protected ref array<float> m_kYaw = {1.256, 0, 1.698, 46.5};
	protected ref array<float> m_kSpin = {1.256, 0, 1.698, -4.5};

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

	protected vector GripWorld(IEntity ear)
	{
		// AMP left cup grip point, cup-rest item-model space (Head pivot, Enfusion axes)
		vector grip = "0.121 0.02358 -0.00699";
		Animation anim = ear.GetAnimation();
		int ic = anim.GetBoneIndex("EP_Cup_L");
		array<vector> rc = m_aRest[0].Get("EP_Cup_L");
		vector now[4];
		anim.GetBoneMatrix(ic, now);
		vector rest[4];
		for (int i = 0; i < 4; i++)
			rest[i] = rc[i];
		vector local = grip.InvMultiply4(rest);
		vector posed = local.Multiply4(now);
		return ear.CoordToParent(posed);
	}

	//------------------------------------------------------------------------------------------------ gadget diagnostics
	protected int m_iG;
	protected float m_fObsUntil = -1;
	protected float m_fObsLast;
	protected IEntity m_ObsGadget;
	protected IEntity m_Proxy2;

	void OnGadgetState(IEntity gadget, bool isInHand, bool isOnGround)
	{
		Log(string.Format("[GSTATE] t=%1 gadget %2 inHand=%3 onGround=%4", Now(), gadget, isInHand, isOnGround));
	}

	protected IEntity FindGadget(IEntity c, EGadgetType type)
	{
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(c.FindComponent(SCR_InventoryStorageManagerComponent));
		array<IEntity> items = {};
		inv.GetItems(items);
		foreach (IEntity it : items)
		{
			SCR_GadgetComponent g = SCR_GadgetComponent.Cast(it.FindComponent(SCR_GadgetComponent));
			if (g && g.GetType() == type)
				return it;
		}
		return null;
	}

	protected void Observe(float secs, IEntity g)
	{
		m_fObsUntil = Now() + secs;
		m_ObsGadget = g;
		m_fObsLast = -1;
	}

	protected bool TickObserve()
	{
		if (m_fObsUntil < 0)
			return false;
		float t = Now();
		if (t > m_fObsUntil)
		{
			m_fObsUntil = -1;
			return false;
		}
		if (t - m_fObsLast >= 0.05)
		{
			m_fObsLast = t;
			IEntity man = m_aMen[0];
			CharacterControllerComponent cc = ChimeraCharacter.Cast(man).GetCharacterController();
			vector lh = BoneWorld(man, "LeftHand") - BoneWorld(man, "Head");
			Log(string.Format("[OBS] t=%1 inHand=%2 leftSlot=%3 wristRelHead %4 weapon %5", t, cc.IsGadgetInHands(), cc.GetAttachedGadgetAtLeftHandSlot() == m_ObsGadget, lh, cc.GetWeaponManagerComponent().GetCurrentWeapon()));
		}
		return true;
	}

	protected void StepGDiag()
	{
		IEntity man;
		if (!m_aMen.IsEmpty())
			man = m_aMen[0];
		CharacterControllerComponent cc;
		if (man)
			cc = ChimeraCharacter.Cast(man).GetCharacterController();
		switch (m_iG)
		{
			case 0:
				HoldFor(5, 120);
				break;
			case 1:
			{
				IEntity pc = null;
				if (GetGame().GetPlayerController())
					pc = GetGame().GetPlayerController().GetControlledEntity();
				if (!pc)
				{
					HoldFor(1, 10);
					return;
				}
				m_aMen.Insert(pc);
				SCR_CharacterControllerComponent scc = SCR_CharacterControllerComponent.Cast(ChimeraCharacter.Cast(pc).GetCharacterController());
				scc.m_OnGadgetStateChangedInvoker.Insert(OnGadgetState);
				Log("player " + pc.ToString());
				HoldFor(2, 30);
				break;
			}
			case 2:
			{
				IEntity compass = FindGadget(man, EGadgetType.COMPASS);
				Log(string.Format("T1 vanilla compass %1", compass));
				if (compass)
				{
					SCR_GadgetComponent gc = SCR_GadgetComponent.Cast(compass.FindComponent(SCR_GadgetComponent));
					Log("T1 take -> " + cc.TakeGadgetInLeftHand(compass, gc.GetAnimVariable(), false, true).ToString());
					Observe(2.0, compass);
				}
				break;
			}
			case 3:
				cc.RemoveGadgetFromHand(true);
				HoldFor(1.5, 30);
				break;
			case 4:
			{
				SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(man.FindComponent(SCR_InventoryStorageManagerComponent));
				m_Proxy = Spawn(PROXY_RAISE_L, man.GetOrigin() + "0 2 0");
				Log(string.Format("proxy inserted %1", inv.TryInsertItem(m_Proxy)));
				cc.SetWeaponRaised(false);
				HoldFor(0.6, 15);
				break;
			}
			case 5:
				Log("T2 proxy, weapon lowered, skip=1 -> " + cc.TakeGadgetInLeftHand(m_Proxy, 0, false, true).ToString());
				Observe(1.5, m_Proxy);
				break;
			case 6:
				cc.RemoveGadgetFromHand(true);
				Log("T3 holster weapon: SelectWeapon(null) -> " + cc.SelectWeapon(null).ToString());
				HoldFor(2.5, 40);
				break;
			case 7:
				Log("T3 proxy, weapon holstered, skip=1 -> " + cc.TakeGadgetInLeftHand(m_Proxy, 0, false, true).ToString());
				Observe(2.6, m_Proxy);
				break;
			case 8:
				cc.RemoveGadgetFromHand(true);
				HoldFor(1.5, 30);
				break;
			case 9:
				Log("T4 proxy, weapon holstered, skip=0 -> " + cc.TakeGadgetInLeftHand(m_Proxy, 0, false, false).ToString());
				Observe(3.5, m_Proxy);
				break;
			case 10:
				cc.RemoveGadgetFromHand(true);
				HoldFor(1.5, 30);
				break;
			case 11:
			{
				SCR_InventoryStorageManagerComponent inv5 = SCR_InventoryStorageManagerComponent.Cast(man.FindComponent(SCR_InventoryStorageManagerComponent));
				m_Proxy2 = Spawn("{9325A03B6F5D334F}Prefabs/PLHM_Test/PLHM_Proxy_CompassGraph.et", man.GetOrigin() + "0 2 0");
				Log(string.Format("T5 compass-graph proxy inserted %1", inv5.TryInsertItem(m_Proxy2)));
				HoldFor(0.6, 15);
				break;
			}
			case 12:
				Log("T5 compass-graph proxy, holstered, skip=1 -> " + cc.TakeGadgetInLeftHand(m_Proxy2, 2, false, true).ToString());
				Observe(2.0, m_Proxy2);
				break;
			case 13:
				cc.RemoveGadgetFromHand(true);
				HoldFor(1.5, 30);
				break;
			case 14:
				Log("T6 our proxy, anim variable 2, holstered, skip=1 -> " + cc.TakeGadgetInLeftHand(m_Proxy, 2, false, true).ToString());
				Observe(2.0, m_Proxy);
				break;
			case 15:
				cc.RemoveGadgetFromHand(true);
				HoldFor(1.0, 20);
				break;
			case 16:
				Log("DONE");
				break;
			default:
				return;
		}
		m_iG++;
	}

	protected void StepHand()
	{
		switch (m_iH)
		{
			case 0:
				System.GetCLIParam("plhmView", m_sView);
				if (m_sView == "")
					m_sView = "left";
				HoldFor(5, 120);
				break;
			case 1:
			{
				// the real use case: the PLAYER's own character (an uncontrolled spawned soldier may be AI-managed)
				IEntity pc = null;
				if (GetGame().GetPlayerController())
					pc = GetGame().GetPlayerController().GetControlledEntity();
				if (!pc)
				{
					HoldFor(1, 10);
					return;
				}
				m_aMen.Insert(pc);
				m_aOwn.Insert(true);
				Log("player character " + pc.ToString());
				HoldFor(3, 60);
				break;
			}
			case 2:
				Log("wear test helmet -> " + Wear(m_aMen[0], TEST_HELMET).ToString());
				HoldFor(2, 30);
				break;
			case 3:
				m_aEar.Insert(InsertIntoHelmet(m_aMen[0], AMP_OWN));
				HoldFor(2, 40);
				break;
			case 4:
			{
				IEntity ear = m_aEar[0];
				Log("independent visual rebuilt=" + EnsureIndependentVisual(ear).ToString());
				ear.SetFlags(EntityFlags.ACTIVE);
				map<string, ref array<vector> > rest;
				CaptureRest(ear, rest);
				m_aRest.Insert(rest);
				Aim(m_aMen[0], m_sView);
				HoldFor(1.5, 40);
				break;
			}
			case 5:
			{
				SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(m_aMen[0].FindComponent(SCR_InventoryStorageManagerComponent));
				string un;
				System.GetCLIParam("plhmUnarmed", un);
				if (un == "1")
					Log("holster weapon -> " + ChimeraCharacter.Cast(m_aMen[0]).GetCharacterController().SelectWeapon(null).ToString());
				m_Proxy = Spawn(PROXY_RAISE_L, m_aMen[0].GetOrigin() + "0 2 0");
				bool ins = m_Proxy && inv.TryInsertItem(m_Proxy);
				Log(string.Format("proxy spawned %1 inserted %2 parent %3", m_Proxy, ins, m_Proxy.GetParent()));
				Aim(m_aMen[0], m_sView);
				HoldFor(2.5, 40);
				break;
			}
			case 6:
			{
				CharacterControllerComponent cc = ChimeraCharacter.Cast(m_aMen[0]).GetCharacterController();
				LogPoseChain("POSE_IDLE", m_aMen[0]);
				Log(string.Format("CanEquipGadget %1", cc.CanEquipGadget(m_Proxy)));
				string sk;
				System.GetCLIParam("plhmSkip", sk);
				bool skip = sk == "1";
				// anim variable 0 = 'no gadget' for the native hand logic -> the item is dropped after the blend (gdiag4);
				// any vanilla value works, 2 (SY183) proven
				bool ok = cc.TakeGadgetInLeftHand(m_Proxy, 2, false, skip);
				Log(string.Format("skipAnimations=%1", skip));
				Log(string.Format("TakeGadgetInLeftHand -> %1", ok));
				m_fT0 = Now();
				m_bAnimating = true;
				m_iShotIdx = 0;
				break;
			}
			case 7:
				Aim(m_aMen[0], m_sView);
				HoldFor(1.0, 30);
				break;
			case 8:
			{
				string f = string.Format("$profile:plhmshots/%1_hand_after_%2.bmp", m_iSnap.ToString(4), m_sView);
				m_iSnap++;
				Log(string.Format("[SNAP] %1 ok=%2", f, System.MakeScreenshot(f)));
				LogEar("AFTER", m_aEar[0], m_aMen[0]);
				break;
			}
			case 9:
				Log("DONE");
				break;
			default:
				return;
		}
		m_iH++;
	}

	//! parent-relative (local) matrices of the spine->head chain: the authoring rig is set to these so the clip and the
	//! head-borne cups agree with the in-game stance
	protected void LogPoseChain(string tag, IEntity man)
	{
		Animation anim = man.GetAnimation();
		foreach (string b : {"Hips", "Spine1", "Spine2", "Spine3", "Spine4", "Spine5", "Neck1", "Neck2", "Neck3", "Head", "LeftShoulder", "RightShoulder"})
		{
			int bi = anim.GetBoneIndex(b);
			if (bi == -1)
				continue;
			vector l[4];
			anim.GetBoneLocalMatrix(bi, l);
			vector ang = Math3D.MatrixToAngles(l);
			float q[4];
			Math3D.MatrixToQuat(l, q);
			Log(string.Format("[%1] %2 t %3 x %4 y %5 z %6", tag, b, l[3], l[0], l[1], l[2]));
		}
	}

	protected bool m_bPoseLoggedGrip;

	protected void TickHand()
	{
		float t = Now() - m_fT0;
		IEntity man = m_aMen[0];
		IEntity ear = m_aEar[0];
		Aim(man, m_sView);
		if (!m_bReleased)
		{
			float sp = KeyValue(m_kSplay, t);
			float sw = KeyValue(m_kSwing, t);
			float yw = KeyValue(m_kYaw, t);
			float sn = KeyValue(m_kSpin, t);
			PoseSide(ear, true, -1, sp, sw, sn, yw, m_aRest[0]);
		}
		CharacterControllerComponent cc = ChimeraCharacter.Cast(man).GetCharacterController();
		if (!m_bPoseLoggedGrip && t >= 0.8)
		{
			m_bPoseLoggedGrip = true;
			LogPoseChain("POSE_GRIP", man);
		}
		if (t - m_fLastLog >= 0.1)
		{
			m_fLastLog = t;
			vector g = GripWorld(ear);
			vector lh = BoneWorld(man, "LeftHand");
			vector lk = BoneWorld(man, "LeftHandMiddle2");
			Log(string.Format("[HAND] t=%1 gadgetInHand=%2 wrist-grip %3 mm knuckle-grip %4 mm wrist %5 grip %6", t, cc.IsGadgetInHands(),
				(int)(vector.Distance(lh, g) * 1000), (int)(vector.Distance(lk, g) * 1000), lh - BoneWorld(man, "Head"), g - BoneWorld(man, "Head")));
		}
		if (m_iShotIdx < m_aShotT.Count() && t >= m_aShotT[m_iShotIdx])
		{
			string f = string.Format("$profile:plhmshots/%1_hand_t%2_%3.bmp", m_iSnap.ToString(4), (int)(m_aShotT[m_iShotIdx] * 100), m_sView);
			m_iSnap++;
			Log(string.Format("[SNAP] %1 ok=%2", f, System.MakeScreenshot(f)));
			m_iShotIdx++;
		}
		if (!m_bReleased && t >= 2.45)
		{
			m_bReleased = true;
			cc.RemoveGadgetFromHand(true);
			Log("RemoveGadgetFromHand(true)");
		}
		if (t >= 2.8)
			m_bAnimating = false;
	}

	//------------------------------------------------------------------------------------------------ probe (SetBoneMatrix semantics)
	protected bool m_bReapply;
	protected int m_iProbeOrder;		// 0 arm only, 1 cup only, 2 arm then cup, 3 cup then arm
	protected float m_fProbeSwing = 90;
	protected float m_fProbeYaw = 45;

	protected void SetOne(IEntity ear, bool own, string bone, vector axisBl, float deg, map<string, ref array<vector> > rest)
	{
		Animation anim = ear.GetAnimation();
		int bi = anim.GetBoneIndex(bone);
		array<vector> r = rest.Get(bone);
		if (bi == -1 || !r)
			return;
		vector R[4], rot[4], d[4];
		for (int i = 0; i < 3; i++)
			R[i] = r[i];
		RotAxis(MapDir(axisBl, own), -deg * Math.DEG2RAD, rot);
		Conj(R, rot, d);
		bool ok = anim.SetBoneMatrix(ear, bi, d);
		if (!m_bReapply)
			Log(string.Format("   set %1 %2 deg ok=%3 delta %4", bone, deg, ok, M2S(d)));
	}

	protected void ApplyProbe(int order)
	{
		for (int i = 0; i < m_aEar.Count(); i++)
		{
			IEntity ear = m_aEar[i];
			if (!ear || m_aRest[i].Count() == 0)
				continue;
			if (order == 0 || order == 2)
				SetOne(ear, m_aOwn[i], "EP_Arm_L", "1 0 0", m_fProbeSwing, m_aRest[i]);
			if (order == 1 || order == 2 || order == 3)
				SetOne(ear, m_aOwn[i], "EP_Cup_L", "0 0 1", -m_fProbeYaw, m_aRest[i]);
			if (order == 3)
				SetOne(ear, m_aOwn[i], "EP_Arm_L", "1 0 0", m_fProbeSwing, m_aRest[i]);
		}
	}

	protected void ResetAll()
	{
		for (int i = 0; i < m_aEar.Count(); i++)
		{
			IEntity ear = m_aEar[i];
			if (!ear || !ear.GetAnimation())
				continue;
			vector id[4];
			Math3D.MatrixIdentity4(id);
			foreach (string b : {"EP_Arm_L", "EP_Arm_R", "EP_Cup_L", "EP_Cup_R"})
			{
				int bi = ear.GetAnimation().GetBoneIndex(b);
				if (bi != -1)
					ear.GetAnimation().SetBoneMatrix(ear, bi, id);
			}
		}
	}

	protected void ShootProbe(string scene)
	{
		for (int i = 0; i < m_aMen.Count(); i++)
		{
			string tag = "INH";
			if (m_aOwn[i])
				tag = "OWN";
			Queue(m_aMen[i], "left", scene + "_" + tag);
			Queue(m_aMen[i], "rear34L", scene + "_" + tag);
		}
	}

	//! NVG Systems' proven workaround (GMS_ZDT_NODMechanismComponent): clothing can give the worn item a visual driven
	//! by the character skeleton (VCFlags.INHERIT_PARENT_SKELETON) - script bone poses then do not reach it.
	//! Recreate the visual as an independent instance of the same mesh.
	static bool EnsureIndependentVisual(IEntity entity)
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

	protected int m_iP2;

	protected void StepProbe2()
	{
		switch (m_iP2)
		{
			case 0:
				for (int i = 0; i < m_aEar.Count(); i++)
				{
					IEntity ear = m_aEar[i];
					if (!ear)
						continue;
					int fl = ear.SetVComponentFlags(0);
					bool inh = (fl & VCFlags.INHERIT_PARENT_SKELETON) != 0;
					Log(string.Format("P2 ear %1 vflags %2 inheritParentSkeleton=%3 vobject %4", i, fl, inh, ear.GetVObject().GetResourceName()));
					if (m_aOwn[i])
					{
						bool rebuilt = EnsureIndependentVisual(ear);
						int fl2 = ear.SetVComponentFlags(0);
						Log(string.Format("P2 ear %1 independent visual rebuilt=%2 vflags now %3", i, rebuilt, fl2));
						ear.SetFlags(EntityFlags.ACTIVE);
					}
				}
				HoldFor(1.0, 30);
				break;
			case 1:
				for (int i = 0; i < m_aEar.Count(); i++)
				{
					if (!m_aEar[i])
						continue;
					LogEar("P2REST" + i.ToString(), m_aEar[i], m_aMen[i]);
					map<string, ref array<vector> > rest;
					CaptureRest(m_aEar[i], rest);
					m_aRest[i] = rest;
				}
				ShootProbe("q0_rebuilt");
				break;
			case 2:
				for (int i = 0; i < m_aEar.Count(); i++)
				{
					if (!m_aEar[i] || m_aRest[i].Count() == 0)
						continue;
					PoseSide(m_aEar[i], m_aOwn[i], -1, 24, 161.5, -4.5, 46.5, m_aRest[i]);
					PoseSide(m_aEar[i], m_aOwn[i], 1, 24, 161.5, -4.5, 46.5, m_aRest[i]);
				}
				HoldFor(1.5, 60);
				break;
			case 3:
				for (int i = 0; i < m_aEar.Count(); i++)
					if (m_aEar[i])
						LogEar("P2STOW" + i.ToString(), m_aEar[i], m_aMen[i]);
				ShootAll("q1_stowed");
				break;
			case 4:
				for (int i = 0; i < m_aEar.Count(); i++)
				{
					if (!m_aEar[i] || m_aRest[i].Count() == 0)
						continue;
					PoseSide(m_aEar[i], m_aOwn[i], -1, 14, 0, 0, 0, m_aRest[i]);
					PoseSide(m_aEar[i], m_aOwn[i], 1, 14, 0, 0, 0, m_aRest[i]);
				}
				HoldFor(1.0, 40);
				break;
			case 5:
				ShootAll("q2_vented");
				break;
			case 6:
				ResetAll();
				HoldFor(1.0, 40);
				break;
			case 7:
				ShootAll("q3_deployed");
				break;
			case 8:
				Log("DONE");
				break;
			default:
				return;
		}
		m_iP2++;
	}

	protected void StepProbe()
	{
		int k = m_iStep - 100;
		int order = k / 3;			// 0..3 single-shot orders, 4 = per-frame re-apply of order 2
		int sub = k % 3;
		if (order > 4)
		{
			Log("DONE");
			m_iStep = 9999;
			return;
		}
		if (sub == 0)
		{
			m_bReapply = false;
			ResetAll();
			Log(string.Format("PROBE order %1 (0 arm only, 1 cup only, 2 arm>cup, 3 cup>arm, 4 per-frame arm>cup)", order));
			if (order == 4)
			{
				m_iProbeOrder = 2;
				m_bReapply = true;
			}
			else
				ApplyProbe(order);
			HoldFor(1.0, 40);
		}
		else if (sub == 1)
		{
			for (int i = 0; i < 2; i++)
				if (m_aEar[i])
					LogEar(string.Format("PROBE%1_%2", order, i), m_aEar[i], m_aMen[i]);
			ShootProbe(string.Format("p%1", order));
		}
		m_iStep++;
	}

	protected void ShootAll(string scene)
	{
		for (int i = 0; i < m_aMen.Count(); i++)
		{
			string tag = "INH";
			if (m_aOwn[i])
				tag = "OWN";
			Queue(m_aMen[i], "left", scene + "_" + tag);
			Queue(m_aMen[i], "rear34L", scene + "_" + tag);
			Queue(m_aMen[i], "rear", scene + "_" + tag);
		}
	}

	protected void StepBones()
	{
		if (m_sMode == "probe" && m_iStep == 5)
			m_iStep = 100;
		if (m_sMode == "probe2" && m_iStep >= 5)
		{
			StepProbe2();
			return;
		}
		if (m_iStep >= 100)
		{
			if (m_iStep < 9999)
				StepProbe();
			return;
		}
		switch (m_iStep)
		{
			case 0:
				HoldFor(5, 120);
				break;
			case 1:
			{
				vector base = GetOrigin();
				base[1] = GetWorld().GetSurfaceY(base[0], base[2]);
				for (int i = 0; i < 2; i++)
				{
					IEntity m = Spawn(MANNEQUIN, base + Vector(-0.8 + 1.6 * i, 0, 0), 0);
					m_aMen.Insert(m);
					m_aOwn.Insert(i == 1);
				}
				HoldFor(3, 60);
				break;
			}
			case 2:
				Log("wear SF helmet -> " + Wear(m_aMen[0], SF_HELMET).ToString());
				Log("wear test helmet -> " + Wear(m_aMen[1], TEST_HELMET).ToString());
				HoldFor(2, 30);
				break;
			case 3:
				m_aEar.Insert(InsertIntoHelmet(m_aMen[0], AMP_INH));
				m_aEar.Insert(InsertIntoHelmet(m_aMen[1], AMP_OWN));
				HoldFor(3, 60);
				break;
			case 4:
			{
				for (int i = 0; i < 2; i++)
				{
					string tag = "INH";
					if (m_aOwn[i])
						tag = "OWN";
					IEntity ear = m_aEar[i];
					if (!ear)
					{
						Log(tag + " [ERR] no ear-pro entity");
						m_aRest.Insert(new map<string, ref array<vector> >());
						continue;
					}
					ear.SetFlags(EntityFlags.ACTIVE);
					LogEar(tag + " REST", ear, m_aMen[i]);
					map<string, ref array<vector> > rest;
					CaptureRest(ear, rest);
					m_aRest.Insert(rest);
				}
				ShootAll("a_rest");
				break;
			}
			case 5:
			{
				// semantics probe: identity on EP_Cup_R only
				for (int i = 0; i < 2; i++)
				{
					IEntity ear = m_aEar[i];
					if (!ear || !ear.GetAnimation())
						continue;
					int ic = ear.GetAnimation().GetBoneIndex("EP_Cup_R");
					if (ic == -1)
						continue;
					vector id[4];
					Math3D.MatrixIdentity4(id);
					bool ok = ear.GetAnimation().SetBoneMatrix(ear, ic, id);
					Log(string.Format("identity on EP_Cup_R (%1) ok=%2", i, ok));
				}
				HoldFor(0.5, 15);
				break;
			}
			case 6:
				for (int i = 0; i < 2; i++)
					if (m_aEar[i])
						LogEar("IDENT" + i.ToString(), m_aEar[i], m_aMen[i]);
				ShootAll("b_identcupR");
				break;
			case 7:
				for (int i = 0; i < 2; i++)
				{
					if (!m_aEar[i] || m_aRest[i].Count() == 0)
						continue;
					PoseSide(m_aEar[i], m_aOwn[i], -1, 24, 161.5, -4.5, 46.5, m_aRest[i]);
					PoseSide(m_aEar[i], m_aOwn[i], 1, 24, 161.5, -4.5, 46.5, m_aRest[i]);
				}
				HoldFor(1.5, 60);			// applied ONCE; the shots below are 60+ frames later (persistence check)
				break;
			case 8:
				for (int i = 0; i < 2; i++)
					if (m_aEar[i])
						LogEar("STOWED" + i.ToString(), m_aEar[i], m_aMen[i]);
				ShootAll("c_stowed");
				break;
			case 9:
				for (int i = 0; i < 2; i++)
				{
					if (!m_aEar[i] || m_aRest[i].Count() == 0)
						continue;
					PoseSide(m_aEar[i], m_aOwn[i], -1, 14, 0, 0, 0, m_aRest[i]);
					PoseSide(m_aEar[i], m_aOwn[i], 1, 14, 0, 0, 0, m_aRest[i]);
				}
				HoldFor(1.0, 40);
				break;
			case 10:
				ShootAll("d_vented");
				break;
			case 11:
				Log("DONE");
				break;
			default:
				return;
		}
		m_iStep++;
	}
}
