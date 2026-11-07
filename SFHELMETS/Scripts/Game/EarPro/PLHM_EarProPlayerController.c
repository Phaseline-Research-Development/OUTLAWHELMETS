// Phaseline Helmets - ear-pro requests (owner client -> server, server -> owner hand proxy), keybinds and radial menu.
//   [  (PLHM_EarProStow, click)  stow / deploy both cups
//   ]  (PLHM_EarProVent, click)  vent / close both cups
//   \  (PLHM_EarProMenu, hold)   radial: each cup on its own (stow / deploy, vent / close), both cups
// Rebindable under Settings > Controls > Phaseline. Every request is validated on the server.

//! radial controller driving the shared (global) radial menu, configured in code
class PLHM_EarProRadialController : SCR_RadialMenuController
{
	void PLHM_EarProRadialController()
	{
		m_RMControls = new SCR_SelectionMenuControllerInputs();
		m_RMControls.m_sOpenAction = "PLHM_EarProMenu";
		m_RMControls.m_bCloseOnReleaseOpen = true;
		m_RMControls.m_bPerformOnClose = true;
		m_RMControls.m_bCloseOnPerform = true;
		m_RMControls.m_bOpenInRoot = true;
		m_RMControls.m_bShowWhileUnconcious = false;
		m_Data = new SCR_SelectionMenuData();
	}
}

modded class SCR_PlayerController
{
	protected int m_iPLHMRetries;

	//! local player: request an ear-pro toggle / action (keybinds and the radial menu call this)
	//! request: PLHM_EEarProRequest toggle or PLHM_EEarProAction; sideMask 1 left, 2 right, 3 both
	void PLHM_RequestEarPro(int request, int sideMask)
	{
		if (Replication.IsServer())
			PLHM_ServerHandleRequest(request, sideMask);
		else
			Rpc(PLHM_RpcAsk_EarPro, request, sideMask);
	}

	[RplRpc(RplChannel.Reliable, RplRcver.Server)]
	protected void PLHM_RpcAsk_EarPro(int request, int sideMask)
	{
		PLHM_ServerHandleRequest(request, sideMask);
	}

	//! server: validate + start for this player's character
	void PLHM_ServerHandleRequest(int request, int sideMask)
	{
		string why;
		if (!PLHM_EarProService.ServerRequest(GetControlledEntity(), request, sideMask, why))
			Print(string.Format("[PLHM] request %1/%2 refused: %3", request, sideMask, why), LogLevel.NORMAL);
	}

	//! server: the owning client takes the proxy (gadget equips are owner-driven and replicate from there)
	void PLHM_ServerTellOwnerTake(IEntity proxy, int clip)
	{
		RplComponent rc = RplComponent.Cast(proxy.FindComponent(RplComponent));
		if (!rc)
			return;
		RplComponent mine = RplComponent.Cast(FindComponent(RplComponent));
		if (mine && mine.IsOwner())
		{
			PLHM_EarProService.LocalTake(GetControlledEntity(), proxy, clip);
			return;
		}
		Rpc(PLHM_RpcDo_Take, rc.Id(), clip);
	}

	[RplRpc(RplChannel.Reliable, RplRcver.Owner)]
	protected void PLHM_RpcDo_Take(RplId id, int clip)
	{
		RplComponent rc = RplComponent.Cast(Replication.FindItem(id));
		if (!rc || !rc.GetEntity())
		{
			// the proxy may arrive a few frames after this RPC
			if (m_iPLHMRetries++ < 20)
				GetGame().GetCallqueue().CallLater(PLHM_RpcDo_Take, 50, false, id, clip);
			return;
		}
		m_iPLHMRetries = 0;
		PLHM_EarProService.LocalTake(GetControlledEntity(), rc.GetEntity(), clip);
	}

	//================================================================================================ input (local player)
	static const ResourceName PLHM_ICONS = "{3262679C50EF4F01}UI/Textures/Icons/icons_wrapperUI.imageset";
	protected ref PLHM_EarProRadialController m_PLHMRadial;
	protected SCR_RadialMenu m_PLHMMenu;
	protected bool m_bPLHMInput;

	override void OnControlledEntityChanged(IEntity from, IEntity to)
	{
		super.OnControlledEntityChanged(from, to);
		if (!m_bPLHMInput && GetGame().GetPlayerController() == this)
			PLHM_InitInput();
	}

	protected void PLHM_InitInput()
	{
		m_bPLHMInput = true;
		InputManager im = GetGame().GetInputManager();
		im.AddActionListener("PLHM_EarProStow", EActionTrigger.DOWN, PLHM_OnStowKey);
		im.AddActionListener("PLHM_EarProVent", EActionTrigger.DOWN, PLHM_OnVentKey);
		im.AddActionListener("PLHM_EarProMenu", EActionTrigger.DOWN, PLHM_OnMenuKey);
		m_PLHMRadial = new PLHM_EarProRadialController();
		m_PLHMRadial.GetOnTakeControl().Insert(PLHM_OnRadialTakeControl);
		m_PLHMRadial.GetOnControllerChanged().Insert(PLHM_OnRadialLostControl);
	}

	protected PLHM_EarProComponent PLHM_MyEarPro()
	{
		return PLHM_EarProService.FindEarPro(GetControlledEntity());
	}

	protected void PLHM_OnStowKey()
	{
		if (PLHM_MyEarPro())
			PLHM_RequestEarPro(PLHM_EEarProRequest.TOGGLE_STOW, 3);
	}

	protected void PLHM_OnVentKey()
	{
		if (PLHM_MyEarPro())
			PLHM_RequestEarPro(PLHM_EEarProRequest.TOGGLE_VENT, 3);
	}

	//------------------------------------------------------------------------------------------------ radial
	protected void PLHM_OnMenuKey()
	{
		PLHM_EarProComponent ep = PLHM_MyEarPro();
		if (!ep || !m_PLHMRadial)
			return;
		if (m_PLHMRadial.IsMenuOpen())
		{
			m_PLHMRadial.CloseMenu();
			return;
		}
		SCR_RadialMenu menu = SCR_RadialMenu.GlobalRadialMenu();
		if (!menu)
			return;
		m_PLHMRadial.Control(this, menu);
		PLHM_FillRadial(menu, ep);
		m_PLHMRadial.OnInputOpen();
	}

	protected void PLHM_OnRadialTakeControl(SCR_RadialMenuController controller)
	{
		m_PLHMMenu = controller.GetRadialMenu();
		if (m_PLHMMenu)
			m_PLHMMenu.GetOnPerform().Insert(PLHM_OnRadialPerform);
	}

	protected void PLHM_OnRadialLostControl(SCR_RadialMenuController controller, bool hasControl)
	{
		if (hasControl || !m_PLHMMenu)
			return;
		m_PLHMMenu.GetOnPerform().Remove(PLHM_OnRadialPerform);
		m_PLHMMenu = null;
	}

	protected void PLHM_AddEntry(SCR_RadialMenu menu, string id, string name, string icon)
	{
		SCR_SelectionMenuEntry e = new SCR_SelectionMenuEntry();
		e.SetId(id);
		e.SetName(name);
		e.SetIcon(PLHM_ICONS, icon);
		menu.AddEntry(e);
	}

	protected void PLHM_FillRadial(SCR_RadialMenu menu, PLHM_EarProComponent ep)
	{
		menu.ClearEntries();
		int l = ep.GetState(PLHM_EarProComponent.SIDE_L);
		int r = ep.GetState(PLHM_EarProComponent.SIDE_R);
		bool both = l == PLHM_EEarProState.STOWED && r == PLHM_EEarProState.STOWED;
		if (ep.CanStow())
		{
			if (both)
				PLHM_AddEntry(menu, "stow_3", "Deploy both cups", "down");
			else
				PLHM_AddEntry(menu, "stow_3", "Stow both cups", "up");
			if (l == PLHM_EEarProState.STOWED)
				PLHM_AddEntry(menu, "stow_1", "Deploy left cup", "veh_left");
			else
				PLHM_AddEntry(menu, "stow_1", "Stow left cup", "veh_left");
			if (r == PLHM_EEarProState.STOWED)
				PLHM_AddEntry(menu, "stow_2", "Deploy right cup", "veh_right");
			else
				PLHM_AddEntry(menu, "stow_2", "Stow right cup", "veh_right");
		}
		if (ep.CanVent())
		{
			if (l == PLHM_EEarProState.VENTED && r != PLHM_EEarProState.DEPLOYED)
				PLHM_AddEntry(menu, "vent_3", "Close both cups", "sound-off");
			else
				PLHM_AddEntry(menu, "vent_3", "Vent both cups", "sound-on");
			if (l == PLHM_EEarProState.VENTED)
				PLHM_AddEntry(menu, "vent_1", "Close left cup", "sound-off");
			else if (l == PLHM_EEarProState.DEPLOYED)
				PLHM_AddEntry(menu, "vent_1", "Vent left cup", "sound-on");
			if (r == PLHM_EEarProState.VENTED)
				PLHM_AddEntry(menu, "vent_2", "Close right cup", "sound-off");
			else if (r == PLHM_EEarProState.DEPLOYED)
				PLHM_AddEntry(menu, "vent_2", "Vent right cup", "sound-on");
		}
	}

	protected void PLHM_OnRadialPerform(SCR_SelectionMenu menu, SCR_SelectionMenuEntry entry)
	{
		if (!entry || !m_PLHMRadial || !m_PLHMRadial.HasControl())
			return;
		string id = entry.GetId();
		if (!id.StartsWith("stow_") && !id.StartsWith("vent_"))
			return;
		int mask = id.Substring(5, 1).ToInt();
		int request = PLHM_EEarProRequest.TOGGLE_STOW;
		if (id.StartsWith("vent_"))
			request = PLHM_EEarProRequest.TOGGLE_VENT;
		PLHM_RequestEarPro(request, mask);
	}
}
