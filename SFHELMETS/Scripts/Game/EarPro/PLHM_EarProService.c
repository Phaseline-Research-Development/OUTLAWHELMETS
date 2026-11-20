// Phaseline Helmets - ear-pro hand proxy + server-side request handling.

//! Invisible "hand" gadget: while in the left hand it injects the PLHM_EarPro graph (reach / grip / manipulate / release).
//! Anim variable passed to TakeGadgetInLeftHand must be non-zero: 0 means "no gadget" to the native hand logic and the
//! item is dropped right after the blend-in (verified 2026-11-06).
[ComponentEditorProps(category: "Phaseline/Helmets", description: "Ear-pro hand proxy gadget")]
class PLHM_EarProHandComponentClass : SCR_GadgetComponentClass
{
}

class PLHM_EarProHandComponent : SCR_GadgetComponent
{
	static const int ANIM_VARIABLE = 2;
}

class PLHM_EarProService
{
	static const int SIDE_B = 3;
	static const float SLING_LEAD = 1.6;			// armed: time allowed to sling the weapon before the clip starts
	static const int SLING_POLL_MS = 50;
	static const int SLING_POLL_MAX = 50;			// 2.5 s at most, then the clip starts anyway

	//! ear-pro item on the character's headgear (helmet ear-pro slot), or null
	static PLHM_EarProComponent FindEarPro(IEntity character)
	{
		if (!character)
			return null;
		SCR_CharacterInventoryStorageComponent cs = SCR_CharacterInventoryStorageComponent.Cast(character.FindComponent(SCR_CharacterInventoryStorageComponent));
		if (!cs)
			return null;
		for (int i = 0; i < cs.GetSlotsCount(); i++)
		{
			InventoryStorageSlot slot = cs.GetSlot(i);
			if (!slot)
				continue;
			IEntity worn = slot.GetAttachedEntity();
			if (!worn)
				continue;
			BaseInventoryStorageComponent st = BaseInventoryStorageComponent.Cast(worn.FindComponent(ClothNodeStorageComponent));
			if (!st)
				continue;
			for (int j = 0; j < st.GetSlotsCount(); j++)
			{
				InventoryStorageSlot s2 = st.GetSlot(j);
				if (!s2 || !s2.GetAttachedEntity())
					continue;
				PLHM_EarProComponent ep = PLHM_EarProComponent.Cast(s2.GetAttachedEntity().FindComponent(PLHM_EarProComponent));
				if (ep)
					return ep;
			}
		}
		return null;
	}

	//! a weapon in the hands: the owner slings it before the clip and brings it back up afterwards (Tyler 2026-11-06)
	static bool IsArmed(IEntity character)
	{
		ChimeraCharacter ch = ChimeraCharacter.Cast(character);
		if (!ch || !ch.GetCharacterController())
			return false;
		BaseWeaponManagerComponent wm = ch.GetCharacterController().GetWeaponManagerComponent();
		return wm && wm.GetCurrentWeapon();
	}

	protected static bool HandsFree(CharacterControllerComponent cc)
	{
		IEntity g = cc.GetAttachedGadgetAtLeftHandSlot();
		if (g && g.FindComponent(PLHM_EarProHandComponent))
			return true;		// our own proxy from the previous step of a sequence
		return !cc.IsGadgetInHands();
	}

	//! movement / body state that blocks working the cups
	static bool CanUseHands(IEntity character, out string why)
	{
		ChimeraCharacter ch = ChimeraCharacter.Cast(character);
		if (!ch || !ch.GetCharacterController())
		{
			why = "no character";
			return false;
		}
		CharacterControllerComponent cc = ch.GetCharacterController();
		if (cc.GetLifeState() != ECharacterLifeState.ALIVE)
		{
			why = "not alive";
			return false;
		}
		if (ch.IsInVehicle())
		{
			why = "in a vehicle";
			return false;
		}
		if (cc.IsSwimming() || cc.IsClimbing() || cc.IsFalling())
		{
			why = "swimming / climbing / falling";
			return false;
		}
		if (cc.IsSprinting())
		{
			why = "sprinting";
			return false;
		}
		if (!HandsFree(cc))
		{
			why = "an item is in the hands";
			return false;
		}
		return true;
	}

	//! server: a player (or AI) asks for a toggle / action on some cups. Returns false (+ why) if nothing starts.
	static bool ServerRequest(IEntity character, int request, int sideMask, out string why)
	{
		if (!Replication.IsServer())
		{
			why = "not server";
			return false;
		}
		if (!CanUseHands(character, why))
			return false;
		PLHM_EarProComponent ep = FindEarPro(character);
		if (!ep)
		{
			why = "no articulated ear-pro";
			return false;
		}
		if (ep.IsBusy())
		{
			why = "busy";
			return false;
		}
		int mask;
		int action = ep.ResolveToggle(request, sideMask, mask);
		if (action == PLHM_EEarProAction.NONE || !ep.CanDo(action, mask))
		{
			why = "nothing to do in this state";
			return false;
		}
		// with a weapon in hand the owner slings it first, then the cups are worked with the character's own hands
		return StartClip(character, ep, PLHM_EarProClips.Find(ep.GetClipSet(), action, mask, false), why);
	}

	//! server: spawn the clip's hand proxy into the character's inventory, flip the state, hand the proxy to the owner
	protected static bool StartClip(IEntity character, PLHM_EarProComponent ep, int clip, out string why)
	{
		if (clip < 0)
		{
			why = "no clip for this action / side";
			return false;
		}
		Resource res = Resource.Load(PLHM_EarProClips.Proxy(clip));
		if (!res || !res.IsValid())
		{
			why = "proxy prefab missing";
			return false;
		}
		EntitySpawnParams sp();
		sp.TransformMode = ETransformMode.WORLD;
		character.GetTransform(sp.Transform);
		IEntity proxy = GetGame().SpawnEntityPrefab(res, GetGame().GetWorld(), sp);
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(character.FindComponent(SCR_InventoryStorageManagerComponent));
		if (!proxy || !inv || !inv.TryInsertItem(proxy))
		{
			if (proxy)
				SCR_EntityHelper.DeleteEntityAndChildren(proxy);
			why = "no inventory room for the hand proxy";
			return false;
		}
		float lead = 0;
		if (IsArmed(character))
			lead = SLING_LEAD;
		ep.Server_BeginTransition(clip, lead);
		float dur = PLHM_EarProClips.Duration(clip);
		GetGame().GetCallqueue().CallLater(ServerCleanup, (dur + lead + 2.5) * 1000, false, proxy, character);
		// the machine that owns the character equips gadgets: a player's client, or the server for AI
		int pid = GetGame().GetPlayerManager().GetPlayerIdFromControlledEntity(character);
		SCR_PlayerController pc = SCR_PlayerController.Cast(GetGame().GetPlayerManager().GetPlayerController(pid));
		if (pid > 0 && pc)
			pc.PLHM_ServerTellOwnerTake(proxy, clip);
		else
			LocalTake(character, proxy, clip);
		Print(string.Format("[PLHM] start clip %1 (%2) player %3 armed %4", clip, PLHM_EarProClips.NameOf(clip), pid, IsArmed(character)), LogLevel.NORMAL);
		why = "ok";
		return true;
	}

	static void ServerCleanup(IEntity proxy, IEntity character)
	{
		if (!proxy || proxy.IsDeleted())
			return;
		if (character)
		{
			CharacterControllerComponent cc = ChimeraCharacter.Cast(character).GetCharacterController();
			if (cc && cc.GetAttachedGadgetAtLeftHandSlot() == proxy)
				cc.RemoveGadgetFromHand(true);
			SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(character.FindComponent(SCR_InventoryStorageManagerComponent));
			if (inv && inv.TryDeleteItem(proxy))
				return;
		}
		SCR_EntityHelper.DeleteEntityAndChildren(proxy);
	}

	//! on the machine that owns the character: sling the weapon in hand (if any), put the proxy in the left hand once
	//! the hands are free (no pouch animation), release it when the clip ends, then bring the weapon back up
	static void LocalTake(IEntity character, IEntity proxy, int clip)
	{
		ChimeraCharacter ch = ChimeraCharacter.Cast(character);
		if (!ch || !proxy || !ch.GetCharacterController())
			return;
		CharacterControllerComponent cc = ch.GetCharacterController();
		BaseWeaponComponent held = null;
		BaseWeaponManagerComponent wm = cc.GetWeaponManagerComponent();
		if (wm)
			held = wm.GetCurrentWeapon();
		if (!held)
		{
			LocalTakeNow(character, proxy, clip, null);
			return;
		}
		bool ok = cc.SelectWeapon(null);
		Print(string.Format("[PLHM] sling %1 -> %2", held.GetOwner(), ok), LogLevel.NORMAL);
		GetGame().GetCallqueue().CallLater(LocalWaitSlung, SLING_POLL_MS, false, character, proxy, clip, held, 0);
	}

	static void LocalWaitSlung(IEntity character, IEntity proxy, int clip, BaseWeaponComponent held, int tries)
	{
		ChimeraCharacter ch = ChimeraCharacter.Cast(character);
		if (!ch || !proxy || proxy.IsDeleted() || !ch.GetCharacterController())
			return;
		BaseWeaponManagerComponent wm = ch.GetCharacterController().GetWeaponManagerComponent();
		if (wm && wm.GetCurrentWeapon() && tries < SLING_POLL_MAX)
		{
			GetGame().GetCallqueue().CallLater(LocalWaitSlung, SLING_POLL_MS, false, character, proxy, clip, held, tries + 1);
			return;
		}
		// a short settle after the sling animation hands the arms back
		GetGame().GetCallqueue().CallLater(LocalTakeNow, 200, false, character, proxy, clip, held);
	}

	static void LocalTakeNow(IEntity character, IEntity proxy, int clip, BaseWeaponComponent redraw)
	{
		ChimeraCharacter ch = ChimeraCharacter.Cast(character);
		if (!ch || !proxy || proxy.IsDeleted() || !ch.GetCharacterController())
			return;
		CharacterControllerComponent cc = ch.GetCharacterController();
		IEntity old = cc.GetAttachedGadgetAtLeftHandSlot();
		if (old && old != proxy && old.FindComponent(PLHM_EarProHandComponent))
			cc.RemoveGadgetFromHand(true);
		cc.TakeGadgetInLeftHand(proxy, PLHM_EarProHandComponent.ANIM_VARIABLE, false, true);
		GetGame().GetCallqueue().CallLater(LocalRelease, PLHM_EarProClips.Duration(clip) * 1000, false, character, proxy, redraw);
	}

	static void LocalRelease(IEntity character, IEntity proxy, BaseWeaponComponent redraw)
	{
		ChimeraCharacter ch = ChimeraCharacter.Cast(character);
		if (!ch || !ch.GetCharacterController())
			return;
		CharacterControllerComponent cc = ch.GetCharacterController();
		if (cc.GetAttachedGadgetAtLeftHandSlot() == proxy)
			cc.RemoveGadgetFromHand(true);
		if (redraw && cc.GetLifeState() == ECharacterLifeState.ALIVE)
			GetGame().GetCallqueue().CallLater(LocalRedraw, 350, false, character, redraw);
	}

	//! bring the slung weapon back up, unless the player already took something else in hand
	static void LocalRedraw(IEntity character, BaseWeaponComponent weapon)
	{
		ChimeraCharacter ch = ChimeraCharacter.Cast(character);
		if (!ch || !weapon || !ch.GetCharacterController())
			return;
		CharacterControllerComponent cc = ch.GetCharacterController();
		if (cc.GetLifeState() != ECharacterLifeState.ALIVE || cc.IsGadgetInHands())
			return;
		BaseWeaponManagerComponent wm = cc.GetWeaponManagerComponent();
		if (wm && wm.GetCurrentWeapon())
			return;
		Print(string.Format("[PLHM] redraw %1 -> %2", weapon.GetOwner(), cc.SelectWeapon(weapon)), LogLevel.NORMAL);
	}
}
